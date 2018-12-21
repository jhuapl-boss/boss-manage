#!/usr/bin/env python3

# Copyright 2016 The Johns Hopkins University Applied Physics Laboratory
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
By default, start the annotation indexing of a channel.  Invokes the 
Index.FindCuboids step function on the given channel.

Can also stop a running indexing process or resume one that's been stopped via
the --stop and --resume flags, respectively.
"""

import argparse
import boto3
import os
import json
from collections import namedtuple
from mysql import connector

import alter_path
from lib import aws
from lib.external import ExternalCalls
from lib import configuration

# When this number of number of write units is consumed updating an entry in
# the id index, a new entry will be created to reduce the cost of adding
# additional morton ids to that id.
NEW_CHUNK_THRESHOLD = 100

RESOLUTION = 0

# Format string for building the first part of step function's arn.
SFN_ARN_PREFIX_FORMAT = 'arn:aws:states:{}:{}:stateMachine:'

#   "lookup_key": "4&4&24&0",   # This is the 192 cuboid test dataset with 249 ids per cuboid.
#   "lookup_key": "8&8&26&0",   # This is the annotation regression test data.
#   "lookup_key": "4&4&24&0",   # This is 1200 cuboid test dataset.
#   "lookup_key": "4&4&30&0",   # This is 1200 cuboid test dataset with only 1s in the cuboids where x > 1.

class ResourceNotFoundException(Exception):
    """
    Raised when unable to locate the id of collection, experiment, or 
    resource.
    """

"""
Container for MySQL connection parameters.

Fields:
    host (str): DB host name or ip address.
    port (str|int): Port to connect to.
    db (str): Name of DB.
    user (str): DB user name.
    password (str): User password.
"""
DbParams = namedtuple('DbParams', ['host', 'port', 'db', 'user', 'password'])

"""
Container that identifies Boss channel.

Fields:
    collection (str): Collection name.
    experiment (str): Experiment name.
    channel (str): Channel name.
"""
ChannelParams = namedtuple(
    'ChannelParams', ['collection', 'experiment', 'channel'])


def get_mysql_params(bosslet_config):
    """
    Get MySQL connection info from Vault.

    Args:
        session (Session): Open boto3 session.
        domain (str): VPC such as integration.boss.

    Returns:
        (DbParams): Connection info from Vault.
    """
    print('Getting MySQL parameters from Vault (slow) . . .')
    with bosslet_config.call.vault() as vault:
        params = vault.read('secret/endpoint/django/db')

    return DbParams(bosslet_config.names.endpoint_db.rds,
                    params['port'],
                    params['name'],
                    params['user'],
                    params['password'])

def get_lookup_key_from_db(bosslet_config, db_params, channel_params):
    """
    Get the lookup key that identifies the annotation channel from the database.

    Args:
        session (Session): Open boto3 session.
        domain (str): VPC such as integration.boss.
        db_params (DbParams): DB connection info.
        channel_params (ChannelParams): Identifies channel.

    Returns:
        (str): Lookup key.
    """
    coll_query = "SELECT id FROM collection WHERE name = %s"
    exp_query = "SELECT id FROM experiment WHERE name = %s"
    chan_query = "SELECT id FROM channel WHERE name = %s"

    print('Tunneling to DB (slow) . . .')
    with bosslet_config.call.tunnel(db_params.host, db_params.port, 'rds') as local_port:
        try:
            sql = connector.connect(
                user=db_params.user, password=db_params.password, 
                port=local_port, database=db_params.db
            )
            try:
                cursor = sql.cursor()
                cursor.execute(coll_query, (channel_params.collection,))
                coll_set = cursor.fetchall()
                if len(coll_set) != 1:
                    raise ResourceNotFoundException(
                        "Can't find collection: {}".format(channel_params.collection))

                cursor.execute(exp_query, (channel_params.experiment,))
                exp_set = cursor.fetchall()
                if len(exp_set) != 1:
                    raise ResourceNotFoundException(
                        "Can't find experiment: {}".format(channel_params.experiment))

                cursor.execute(chan_query, (channel_params.channel,))
                chan_set = cursor.fetchall()
                if len(chan_set) != 1:
                    raise ResourceNotFoundException(
                        "Can't find channel: {}".format(channel_params.experiment))
            finally:
                cursor.close()
        finally:
            sql.close()

    return '{}&{}&{}&{}'.format(
        coll_set[0][0], exp_set[0][0], chan_set[0][0], RESOLUTION)


def get_common_args(bosslet_config):
    """
    Get common arguments for starting step functions related to indexing.

    Args:
        domain (str): VPC such as integration.boss.
        account (str): AWS account number.
        region (str): AWS region.

    Returns:
        (dict): Arguments.
    """
    sfn_arn_prefix = SFN_ARN_PREFIX_FORMAT.format(bosslet_config.REGION,
                                                  bosslet_config.ACCOUNT_ID)
    n = bosslet_config.names
    common_args = {
        "id_supervisor_step_fcn": '{}{}'.format(sfn_arn_prefix, n.sfn.index_supervisor),
        "id_cuboid_supervisor_step_fcn": '{}{}'.format(sfn_arn_prefix, n.sfn.index_cuboid_supervisor),
        "index_dequeue_cuboids_step_fcn":'{}{}'.format(sfn_arn_prefix, n.sfn.index_dequeue_cuboids),
        "id_index_step_fcn": '{}{}'.format(sfn_arn_prefix, n.sfn.index_id_writer),
        "batch_enqueue_cuboids_step_fcn": '{}{}'.format(sfn_arn_prefix, n.sfn.index_enqueue_cuboids),
        "fanout_enqueue_cuboids_step_fcn": '{}{}'.format(sfn_arn_prefix, n.sfn.index_fanout_enqueue_cuboids),
        "fanout_id_writers_step_fcn": '{}{}'.format(sfn_arn_prefix, n.sfn.index_fanout_id_writers),
        "cuboid_ids_bucket": n.s3.cuboid_ids_bucket,
        "config": {
          "object_store_config": {
            "id_count_table": n.ddb.id_count_index,
            "page_in_lambda_function": n.lambda_.multi_lambda,
            "page_out_lambda_function": n.lambda_.multi_lambda,
            "cuboid_bucket": n.s3.cuboid_bucket,
            "s3_index_table": n.ddb.s3_index,
            "id_index_table": n.ddb.id_index,
            "s3_flush_queue": 'https://queue.amazonaws.com/{}/{}'.format(account, n.sqs.s3flush),
            "id_index_new_chunk_threshold": NEW_CHUNK_THRESHOLD,
            "index_deadletter_queue": 'https://queue.amazonaws.com/{}/{}'.format(account, n.sqs.index_deadletter),
            "index_cuboids_keys_queue": 'https://queue.amazonaws.com/{}/{}'.format(account, n.sqs.index_cuboids_keys)
          },
          "kv_config": {
            "cache_host": n.redis.cache,
            "read_timeout": 86400,
            "cache_db": "0"
          },
          "state_config": {
            "cache_state_db": "0",
            "cache_state_host": n.redis.cache_state
          }
        },
        "max_write_id_index_lambdas": 599,
        "max_cuboid_fanout": 30,
        "max_items": 100
    }

    return common_args


def get_find_cuboid_args(bosslet_config, lookup_key):
    """
    Get all arguments needed to start Index.FindCuboids.

    Args:
        domain (str): VPC such as integration.boss.
        account (str): AWS account number.
        region (str): AWS region.

    Returns:
        (str, str): [0] is the ARN of Index.FindCuboids; [1] are the step function arguments as a JSON string.
    """

    sfn_arn_prefix = SFN_ARN_PREFIX_FORMAT.format(bosslet_config.REGION,
                                                  bosslet_config.ACCOUNT_ID)
    arn = '{}{}'.format(sfn_arn_prefix, bosslet_config.names.index_find_cuboids.sfn)

    find_cuboid_args = get_common_args(bosslet_config)
    find_cuboid_args['lookup_key'] = lookup_key
    return arn, json.dumps(find_cuboid_args)


def get_running_step_fcns(bosslet_config, arn):
    """
    Retrive execution arns of running step functions.

    Args:
        arn (str): Specifies step function of interest.

    Yields:
        (str): Execution arn of running step function.
    """
    sfn = bosslet_config.session.client('stepfunctions')
    list_args = dict(
        stateMachineArn=arn, statusFilter='RUNNING', maxResults=100)

    resp = sfn.list_executions(**list_args)

    for exe in resp['executions']:
        yield exe['executionArn']

    while 'nextToken' in resp:
        list_args['nextToken'] = resp['nextToken']
        resp = sfn.list_executions(**list_args)
        for exe in resp['executions']:
            yield exe['executionArn']


def run_find_cuboids(bosslet_config, args):
    """
    Start Index.FindCuboids.  This step function kicks off the entire indexing
    process from the beginning.

    Args:
        session (Session): An open boto3 Session.
        args (Namespace): Parsed command line arguments.
        account (str): AWS account id.
    """
    channel_params = ChannelParams(
        args.collection, args.experiment, args.channel)

    if args.lookup_key is not None:
        lookup_key = args.lookup_key 
    else:
        # Get DB params from Vault and tunnel to the DB and get lookup_key.
        # Slow!
        mysql_params = get_mysql_params(bosslet_config)
        #print(mysql_params)

        lookup_key = get_lookup_key_from_db(bosslet_config,
                                            mysql_params,
                                            channel_params) 
        print('lookup_key is: {}'.format(lookup_key))

    find_cuboid_args = get_find_cuboid_args(bosslet_config,
                                            lookup_key)
    #print(find_cuboid_args[1])

    print('Starting Index.FindCuboids . . .')
    sfn = bosslet_config.session.client('stepfunctions')
    resp = sfn.start_execution(
        stateMachineArn=find_cuboid_args[0],
        input=find_cuboid_args[1]
    )
    print(resp)


def resume_indexing(bosslet_config):
    """
    Resume indexing a channel or channels.  If the CuboidsKeys queue is not
    empty, indexing will resume on those cuboids identified in that queue.

    Args:
        session (Session): An open boto3 Session.
        region (str): AWS region such as us-east-1.
        account (str): AWS account id.
        domain (str): VPC domain such as production.boss.
    """
    resume_args = get_common_args(bosslet_config):
    resume_args['queue_empty'] = False
    arn = resume_args['id_supervisor_step_fcn']

    print('Resuming indexing (starting Index.Supervisor) . . .')
    sfn = bosslet_config.session.client('stepfunctions')
    resp = sfn.start_execution(
        stateMachineArn=arn,
        input=json.dumps(resume_args)
    )
    print(resp)


def stop_indexing(bosslet_config):
    """
    Stop the indexing process, gracefully.  Index.CuboidSupervisors will not
    be stopped, so the entire index process will not terminate, immediately.
    Only the Index.Supervisor and any running Index.DequeueCuboid step 
    functions will be halted.  This allows the indexing process to be resumed.

    Args:
        session (Session): An open boto3 Session.
        region (str): AWS region such as us-east-1.
        account (str): AWS account id.
        domain (str): VPC domain such as production.boss.
    """
    stop_args = get_common_args(bosslet_config)

    # This error could optionally be caught inside a step function if special
    # shutdown behavior required.
    error = 'ManualAbort'
    cause = 'User initiated abort'

    supe_arn = stop_args['id_supervisor_step_fcn']
    sfn = session.client('stepfunctions')

    print('Stopping Index.Supervisor . . .')
    for arn in get_running_step_fcns(bosslet_config, supe_arn):
        print('\tStopping {}'.format(arn))
        sfn.stop_execution(
            executionArn=arn,
            error=error,
            cause=cause)

    print('Stopping Index.DequeueCuboids . . .')
    deque_arn = stop_args['index_dequeue_cuboids_step_fcn']
    for arn in get_running_step_fcns(bosslet_config, deque_arn):
        print('\tStopping {}'.format(arn))
        sfn.stop_execution(
            executionArn=arn,
            error=error,
            cause=cause)

    print('Done.')


def parse_args():
    """
    Parse command line or config file.

    Returns:
        (Namespace): Parsed arguments.
    """
    parser = configuration.BossParser(
        description='Script for starting annotation index process. ' + 
        'To supply arguments from a file, provide the filename prepended with an `@`.',
        fromfile_prefix_chars = '@')
    parser.add_argument(
        '--lookup-key', '-l',
        default=None,
        help='Lookup key of channel (supply this to avoid slow tunneling to DB)')
    parser.add_argument(
        '--stop',
        action='store_true',
        help='Stop indexing operation (will leave CuboidKeys queue untouched so indexing may be resumed)')
    parser.add_argument(
        '--resume',
        action='store_true',
        help='Resume indexing operation (if CuboidKeys queue still has messages, indexing will resume)')
    parser.add_bosslet("Bosslet name where the lambda functions live")
    parser.add_argument(
        'collection',
        nargs='?',
        default=None,
        help='Name of collection')
    parser.add_argument(
        'experiment',
        nargs='?',
        default=None,
        help='Name of experiment')
    parser.add_argument(
        'channel',
        nargs='?',
        default=None,
        help='Name of channel')

    args = parser.parse_args()

    if args.stop and args.resume:
        parser.print_usage()
        parser.exit(
            1, 'Error: cannot specify --stop and --resume simultaneously')

    if (args.lookup_key is None and not args.stop and not args.resume and
        (args.collection is None or args.experiment is None or args.channel is None)
    ):
        parser.print_usage()
        parser.exit(1, 'Error: must specify collection, experiment, and channel')

    if (args.lookup_key is not None and
        (args.collection is not None or args.experiment is not None or args.channel is not None)
    ):
        print('lookup-key specified, ignoring collection/experiment/channel name(s)')

    return args


if __name__ == '__main__':
    args = parse_args()

    if args.stop:
        stop_indexing(args.bosslet_config)
    elif args.resume:
        resume_indexing(args.bosslet_config)
    else:
        run_find_cuboids(args.bosslet_config, args)


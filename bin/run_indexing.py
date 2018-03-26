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

import alter_path
import argparse
import boto3
from collections import namedtuple
import json
from lib import aws
from lib.external import ExternalCalls
from lib.hosts import PROD_ACCOUNT, DEV_ACCOUNT
from lib.names import AWSNames
from mysql import connector
import os

# When this number of number of write units is consumed updating an entry in
# the id index, a new entry will be created to reduce the cost of adding
# additional morton ids to that id.
NEW_CHUNK_THRESHOLD = 100

DB_HOST_NAME = 'endpoint-db'
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


def get_account(domain):
    """
    Return the AWS account number based on the domain.  The account number is
    used to assemble the step function arns.

    Args:
        domain (str): VPC such as integration.boss.

    Returns:
        (str): AWS account number.
    """
    if domain == 'production.boss' or domain == 'integration.boss':
        return PROD_ACCOUNT
    return DEV_ACCOUNT


def get_mysql_params(session, domain):
    """
    Get MySQL connection info from Vault.

    Args:
        session (Session): Open boto3 session.
        domain (str): VPC such as integration.boss.

    Returns:
        (DbParams): Connection info from Vault.
    """
    keypair = aws.keypair_lookup(session)
    call = ExternalCalls(session, keypair, domain)
    names = AWSNames(domain)

    names = AWSNames(domain)
    print('Getting MySQL parameters from Vault (slow) . . .')
    with call.vault() as vault:
        params = vault.read('secret/endpoint/django/db')

    return DbParams(
        '{}.{}'.format(DB_HOST_NAME, args.domain), params['port'], 
        params['name'], params['user'], params['password'])


def get_lookup_key_from_db(session, domain, db_params, channel_params):
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
    keypair = aws.keypair_lookup(session)
    call = ExternalCalls(session, keypair, domain)

    coll_query = "SELECT id FROM collection WHERE name = %s"
    exp_query = "SELECT id FROM experiment WHERE name = %s"
    chan_query = "SELECT id FROM channel WHERE name = %s"

    print('Tunneling to DB (slow) . . .')
    with call.tunnel(db_params.host, db_params.port, 'rds') as local_port:
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


def get_common_args(domain, account, region):
    """
    Get common arguments for starting step functions related to indexing.

    Args:
        domain (str): VPC such as integration.boss.
        account (str): AWS account number.
        region (str): AWS region.

    Returns:
        (dict): Arguments.
    """
    names = AWSNames(domain)
    sfn_arn_prefix = SFN_ARN_PREFIX_FORMAT.format(region, account)
    common_args = {
        "id_supervisor_step_fcn": '{}{}'.format(sfn_arn_prefix, names.index_supervisor_sfn),
        "id_cuboid_supervisor_step_fcn": '{}{}'.format(sfn_arn_prefix, names.index_cuboid_supervisor_sfn),
        "index_dequeue_cuboids_step_fcn":'{}{}'.format(sfn_arn_prefix, names.index_dequeue_cuboids_sfn),
        "id_index_step_fcn": '{}{}'.format(sfn_arn_prefix, names.index_id_writer_sfn),
        "batch_enqueue_cuboids_step_fcn": '{}{}'.format(sfn_arn_prefix, names.index_enqueue_cuboids_sfn),
        "fanout_enqueue_cuboids_step_fcn": '{}{}'.format(sfn_arn_prefix, names.index_fanout_enqueue_cuboids_sfn),
        "fanout_id_writers_step_fcn": '{}{}'.format(sfn_arn_prefix, names.index_fanout_id_writers_sfn),
        "cuboid_ids_bucket": names.cuboid_ids_bucket,
        "config": {
          "object_store_config": {
            "id_count_table": names.id_count_index,
            "page_in_lambda_function": names.multi_lambda,
            "page_out_lambda_function": names.multi_lambda,
            "cuboid_bucket": names.cuboid_bucket,
            "s3_index_table": names.s3_index,
            "id_index_table": names.id_index,
            "s3_flush_queue": 'https://queue.amazonaws.com/{}/{}'.format(account, names.s3flush_queue),
            "id_index_new_chunk_threshold": NEW_CHUNK_THRESHOLD,
            "index_deadletter_queue": 'https://queue.amazonaws.com/{}/{}'.format(account, names.index_deadletter_queue),
            "index_cuboids_keys_queue": 'https://queue.amazonaws.com/{}/{}'.format(account, names.index_cuboids_keys_queue)
          },
          "kv_config": {
            "cache_host": names.cache,
            "read_timeout": 86400,
            "cache_db": "0"
          },
          "state_config": {
            "cache_state_db": "0",
            "cache_state_host": names.cache_state
          }
        },
        "max_write_id_index_lambdas": 599,
        "max_cuboid_fanout": 30,
        "max_items": 100
    }

    return common_args


def get_find_cuboid_args(domain, account, region, lookup_key):
    """
    Get all arguments needed to start Index.FindCuboids.

    Args:
        domain (str): VPC such as integration.boss.
        account (str): AWS account number.
        region (str): AWS region.

    Returns:
        (str, str): [0] is the ARN of Index.FindCuboids; [1] are the step function arguments as a JSON string.
    """

    names = AWSNames(domain)
    sfn_arn_prefix = SFN_ARN_PREFIX_FORMAT.format(region, account)
    arn = '{}{}'.format(sfn_arn_prefix, names.index_find_cuboids_sfn)

    find_cuboid_args = get_common_args(domain, account, region)
    find_cuboid_args['lookup_key'] = lookup_key
    return arn, json.dumps(find_cuboid_args)


def get_running_step_fcns(arn):
    """
    Retrive execution arns of running step functions.

    Args:
        arn (str): Specifies step function of interest.

    Yields:
        (str): Execution arn of running step function.
    """
    sfn = boto3.client('stepfunctions')
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


def run_find_cuboids(session, args, account):
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
        mysql_params = get_mysql_params(session, args.domain)
        #print(mysql_params)

        lookup_key = get_lookup_key_from_db(
            session, args.domain, mysql_params, channel_params) 
        print('lookup_key is: {}'.format(lookup_key))

    find_cuboid_args = get_find_cuboid_args(
        args.domain, account, args.region, lookup_key)
    #print(find_cuboid_args[1])

    print('Starting Index.FindCuboids . . .')
    sfn = session.client('stepfunctions')
    resp = sfn.start_execution(
        stateMachineArn=find_cuboid_args[0],
        input=find_cuboid_args[1]
    )
    print(resp)


def resume_indexing(session, region, account, domain):
    """
    Resume indexing a channel or channels.  If the CuboidsKeys queue is not
    empty, indexing will resume on those cuboids identified in that queue.

    Args:
        session (Session): An open boto3 Session.
        region (str): AWS region such as us-east-1.
        account (str): AWS account id.
        domain (str): VPC domain such as production.boss.
    """
    names = AWSNames(domain)

    resume_args = get_common_args(domain, account, region)
    resume_args['queue_empty'] = False
    arn = resume_args['id_supervisor_step_fcn']

    print('Resuming indexing (starting Index.Supervisor) . . .')
    sfn = session.client('stepfunctions')
    resp = sfn.start_execution(
        stateMachineArn=arn,
        input=json.dumps(resume_args)
    )
    print(resp)


def stop_indexing(session, region, account, domain):
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
    names = AWSNames(domain)
    sfn_arn_prefix = 'arn:aws:states:{}:{}:stateMachine:'.format(region, account)
    stop_args = get_common_args(domain, account, region)

    # This error could optionally be caught inside a step function if special
    # shutdown behavior required.
    error = 'ManualAbort'
    cause = 'User initiated abort'

    supe_arn = stop_args['id_supervisor_step_fcn']
    sfn = session.client('stepfunctions')

    print('Stopping Index.Supervisor . . .')
    for arn in get_running_step_fcns(supe_arn):
        print('\tStopping {}'.format(arn))
        sfn.stop_execution(
            executionArn=arn,
            error=error,
            cause=cause)

    print('Stopping Index.DequeueCuboids . . .')
    deque_arn = stop_args['index_dequeue_cuboids_step_fcn']
    for arn in get_running_step_fcns(deque_arn):
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
    parser = argparse.ArgumentParser(
        description='Script for starting annotation index process. ' + 
        'To supply arguments from a file, provide the filename prepended with an `@`.',
        fromfile_prefix_chars = '@')
    parser.add_argument(
        '--aws-credentials', '-a',
        metavar='<file>',
        default=os.environ.get('AWS_CREDENTIALS'),
        type=argparse.FileType('r'),
        help='File with credentials for connecting to AWS (default: AWS_CREDENTIALS)')
    parser.add_argument(
        '--region', '-r',
        default='us-east-1',
        help='AWS region (default: us-east-1)')
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
    parser.add_argument(
        'domain',
        help='Domain that lambda functions live in, such as integration.boss')
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

    if args.aws_credentials is None:
        parser.print_usage()
        parser.exit(
            1, 'Error: AWS credentials not provided and AWS_CREDENTIALS is not defined')

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

    session = aws.create_session(args.aws_credentials)
    account = get_account(args.domain)

    if args.stop:
        stop_indexing(session, args.region, account, args.domain)
    elif args.resume:
        resume_indexing(session, args.region, account, args.domain)
    else:
        run_find_cuboids(session, args, account)

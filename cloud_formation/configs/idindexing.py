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

import json
from lib.cloudformation import CloudFormationConfiguration, Ref, Arn, get_scenario, Arg
from lib.userdata import UserData
from lib.names import AWSNames
from lib import aws
from lib import constants as const
from lib import stepfunctions as sfn
from update_lambda_fcn import load_lambdas_on_s3, update_lambda_code

"""
This CloudFormation config file creates the step functions and lambdas used
for annotation (object) id indexing.  When building from scratch, it should
be run after the CloudFormation cachedb config.
"""

def get_bucket_life_cycle_rules():
    """
    Generate the expiration policy for the cuboid_ids bucket.  This bucket
    is a temporary holding place for cuboid ids passed between step function
    states.  Because data passed between states is limited to 32K, the bucket
    is used, instead, to ensure data limits aren't exceeded.
    """
    return {
        'Rules': [
            {
                'ExpirationInDays': 2,
                'Status': 'Enabled'
            }
        ]
    }

def create_config(session, domain):
    """Create the CloudFormationConfiguration object."""
    config = CloudFormationConfiguration('idindexing', domain, const.REGION)
    names = AWSNames(domain)

    #topic_arn = aws.sns_topic_lookup(session, "ProductionMicronsMailingList")

    role = aws.role_arn_lookup(session, "lambda_cache_execution")
    config.add_arg(Arg.String(
        "LambdaCacheExecutionRole", role,
        "IAM role for multilambda." + domain))

    cuboid_ids_bucket_name = names.cuboid_ids_bucket
    if not aws.s3_bucket_exists(session, cuboid_ids_bucket_name):
        life_cycle_cfg = get_bucket_life_cycle_rules()
        config.add_s3_bucket(
            'cuboidIdsBucket', cuboid_ids_bucket_name, 
            life_cycle_config=life_cycle_cfg)

    config.add_s3_bucket_policy(
        "cuboidBucketPolicy", cuboid_ids_bucket_name,
        ['s3:GetObject', 's3:PutObject'],
        { 'AWS': role})

    lambda_bucket = aws.get_lambda_s3_bucket(session)
    config.add_lambda(
        "indexS3WriterLambda",
        names.index_s3_writer_lambda,
        Ref("LambdaCacheExecutionRole"),
        s3=(aws.get_lambda_s3_bucket(session),
            "multilambda.{}.zip".format(domain),
            "write_s3_index_lambda.handler"),
        timeout=120,
        memory=1024,
        runtime='python3.6')

    config.add_lambda(
        "indexFanoutIdWriterLambda",
        names.index_fanout_id_writer_lambda,
        Ref("LambdaCacheExecutionRole"),
        s3=(aws.get_lambda_s3_bucket(session),
            "multilambda.{}.zip".format(domain),
            "fanout_write_id_index_lambda.handler"),
        timeout=120,
        memory=256,
        runtime='python3.6')

    config.add_lambda(
        "indexWriteIdLambda",
        names.index_write_id_lambda,
        Ref("LambdaCacheExecutionRole"),
        s3=(aws.get_lambda_s3_bucket(session),
            "multilambda.{}.zip".format(domain),
            "write_id_index_lambda.handler"),
        timeout=120,
        memory=512,
        runtime='python3.6')

    config.add_lambda(
        "indexWriteFailedLambda",
        names.index_write_failed_lambda,
        Ref("LambdaCacheExecutionRole"),
        s3=(aws.get_lambda_s3_bucket(session),
            "multilambda.{}.zip".format(domain),
            "write_index_failed_lambda.handler"),
        timeout=60,
        memory=128,
        runtime='python3.6')

    config.add_lambda(
        "indexFindCuboidsLambda",
        names.index_find_cuboids_lambda,
        Ref("LambdaCacheExecutionRole"),
        s3=(aws.get_lambda_s3_bucket(session),
            "multilambda.{}.zip".format(domain),
            "index_find_cuboids_lambda.handler"),
        timeout=120,
        memory=256,
        runtime='python3.6')

    config.add_lambda(
        "indexFanoutEnqueueCuboidsKeysLambda",
        names.index_fanout_enqueue_cuboid_keys_lambda,
        Ref("LambdaCacheExecutionRole"),
        s3=(aws.get_lambda_s3_bucket(session),
            "multilambda.{}.zip".format(domain),
            "fanout_enqueue_cuboid_keys_lambda.handler"),
        timeout=120,
        memory=256,
        runtime='python3.6')

    config.add_lambda(
        "indexBatchEnqueueCuboidsLambda",
        names.index_batch_enqueue_cuboids_lambda,
        Ref("LambdaCacheExecutionRole"),
        s3=(aws.get_lambda_s3_bucket(session),
            "multilambda.{}.zip".format(domain),
            "batch_enqueue_cuboids_lambda.handler"),
        timeout=60,
        memory=128,
        runtime='python3.6')

    config.add_lambda(
        "startSfnLambda",
        names.start_sfn_lambda,
        Ref("LambdaCacheExecutionRole"),
        s3=(aws.get_lambda_s3_bucket(session),
            "multilambda.{}.zip".format(domain),
            "start_sfn_lambda.handler"),
        timeout=60,
        memory=128,
        runtime='python3.6')

    config.add_lambda(
        "indexFanoutDequeueCuboidKeysLambda",
        names.index_fanout_dequeue_cuboid_keys_lambda,
        Ref("LambdaCacheExecutionRole"),
        s3=(aws.get_lambda_s3_bucket(session),
            "multilambda.{}.zip".format(domain),
            "fanout_dequeue_cuboid_keys_lambda.handler"),
        timeout=60,
        memory=128,
        runtime='python3.6')

    config.add_lambda(
        "indexDequeueCuboidKeysLambda",
        names.index_dequeue_cuboid_keys_lambda,
        Ref("LambdaCacheExecutionRole"),
        s3=(aws.get_lambda_s3_bucket(session),
            "multilambda.{}.zip".format(domain),
            "dequeue_cuboid_keys_lambda.handler"),
        timeout=60,
        memory=128,
        runtime='python3.6')

    config.add_lambda(
        "indexGetNumCuboidKeysMsgsLambda",
        names.index_get_num_cuboid_keys_msgs_lambda,
        Ref("LambdaCacheExecutionRole"),
        s3=(aws.get_lambda_s3_bucket(session),
            "multilambda.{}.zip".format(domain),
            "get_num_msgs_cuboid_keys_queue_lambda.handler"),
        timeout=60,
        memory=128,
        runtime='python3.6')

    config.add_lambda(
        "indexCheckForThrottlingLambda",
        names.index_check_for_throttling_lambda,
        Ref("LambdaCacheExecutionRole"),
        s3=(aws.get_lambda_s3_bucket(session),
            "multilambda.{}.zip".format(domain),
            "check_for_index_throttling_lambda.handler"),
        timeout=60,
        memory=128,
        runtime='python3.6')

    config.add_lambda(
        "indexInvokeIndexSupervisorLambda",
        names.index_invoke_index_supervisor_lambda,
        Ref("LambdaCacheExecutionRole"),
        s3=(aws.get_lambda_s3_bucket(session),
            "multilambda.{}.zip".format(domain),
            "invoke_index_supervisor_lambda.handler"),
        timeout=60,
        memory=128,
        runtime='python3.6')

    config.add_lambda(
        "indexSplitCuboidsLambda",
        names.index_split_cuboids_lambda,
        Ref("LambdaCacheExecutionRole"),
        s3=(aws.get_lambda_s3_bucket(session),
            "multilambda.{}.zip".format(domain),
            "split_cuboids_lambda.handler"),
        timeout=120,
        memory=128,
        runtime='python3.6')

    config.add_lambda(
        "indexLoadIdsFromS3Lambda",
        names.index_load_ids_from_s3_lambda,
        Ref("LambdaCacheExecutionRole"),
        s3=(aws.get_lambda_s3_bucket(session),
            "multilambda.{}.zip".format(domain),
            "load_ids_from_s3_lambda.handler"),
        timeout=120,
        memory=128,
        runtime='python3.6')

    return config


def generate(session, domain):
    """Create the configuration and save it to disk."""
    config = create_config(session, domain)
    config.generate()


def create(session, domain):
    """Create the configuration and launch."""
    resp = input('Rebuild multilambda: [Y/n]:')
    if len(resp) == 0 or (len(resp) > 0 and resp[0] in ('Y', 'y')):
        pre_init(session, domain)

    config = create_config(session, domain)

    success = config.create(session)
    if success:
        post_init(session, domain)


def pre_init(session, domain):
    """Build multilambda zip file and put in S3."""
    bucket = aws.get_lambda_s3_bucket(session)
    load_lambdas_on_s3(session, domain, bucket)


def post_init(session, domain):
    """Create step functions."""
    names = AWSNames(domain)

    sfn.create(
        session, names.index_supervisor_sfn, domain, 
        'index_supervisor.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(
        session, names.index_cuboid_supervisor_sfn, domain, 
        'index_cuboid_supervisor.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(
        session, names.index_id_writer_sfn, domain, 
        'index_id_writer.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(
        session, names.index_find_cuboids_sfn, domain, 
        'index_find_cuboids.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(
        session, names.index_enqueue_cuboids_sfn, domain, 
        'index_enqueue_cuboids.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(
        session, names.index_fanout_enqueue_cuboids_sfn, domain, 
        'index_fanout_enqueue_cuboids.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(
        session, names.index_dequeue_cuboids_sfn, domain, 
        'index_dequeue_cuboids.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(
        session, names.index_fanout_id_writers_sfn, domain, 
        'index_fanout_id_writers.hsd', 'StatesExecutionRole-us-east-1 ')


def update(session, domain):
    resp = input('Rebuild multilambda: [Y/n]:')
    if len(resp) == 0 or (len(resp) > 0 and resp[0] in ('Y', 'y')):
        pre_init(session, domain)
        bucket = aws.get_lambda_s3_bucket(session)
        update_lambda_code(session, domain, bucket)

    config = create_config(session, domain)
    success = config.update(session)

    if not success:
        return False

    resp = input('Replace step functions: [Y/n]:')
    if len(resp) == 0 or (len(resp) > 0 and resp[0] in ('Y', 'y')):
        delete_sfns(session, domain)
        post_init(session, domain)

    return True


def delete(session, domain):
    #CloudFormationConfiguration('idindexing', domain).delete(session)
    delete_sfns(session, domain)


def delete_sfns(session, domain):
    names = AWSNames(domain)
    sfn.delete(session, names.index_fanout_id_writers_sfn)
    sfn.delete(session, names.index_dequeue_cuboids_sfn)
    sfn.delete(session, names.index_fanout_enqueue_cuboids_sfn)
    sfn.delete(session, names.index_enqueue_cuboids_sfn)
    sfn.delete(session, names.index_find_cuboids_sfn)
    sfn.delete(session, names.index_id_writer_sfn)
    sfn.delete(session, names.index_cuboid_supervisor_sfn)
    sfn.delete(session, names.index_supervisor_sfn)


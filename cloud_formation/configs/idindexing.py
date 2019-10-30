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
from lib.cloudformation import CloudFormationConfiguration, Ref, Arn, Arg
from lib.userdata import UserData
from lib import aws
from lib import utils
from lib import console
from lib import constants as const
from lib import stepfunctions as sfn
from lib.lambdas import load_lambdas_on_s3, update_lambda_code

"""
This CloudFormation config file creates the step functions and lambdas used
for annotation (object) id indexing.  When building from scratch, it should
be run after the CloudFormation cachedb config.
"""

DEPENDENCIES = ['activities', 'cachedb']

def STEP_FUNCTIONS(bosslet_config):
    names = bosslet_config.names
    return [
        (names.index_supervisor.sfn, 'index_supervisor.hsd'),
        (names.index_cuboid_supervisor.sfn, 'index_cuboid_supervisor.hsd'),
        (names.index_id_writer.sfn, 'index_id_writer.hsd'),
        (names.index_find_cuboids.sfn, 'index_find_cuboids.hsd'),
        (names.index_enqueue_cuboids.sfn, 'index_enqueue_cuboids.hsd'),
        (names.index_fanout_enqueue_cuboids.sfn, 'index_fanout_enqueue_cuboids.hsd'),
        (names.index_dequeue_cuboids.sfn, 'index_dequeue_cuboids.hsd'),
        (names.index_fanout_id_writers.sfn, 'index_fanout_id_writers.hsd'),
    ]


def create_config(bosslet_config):
    """Create the CloudFormationConfiguration object."""
    config = CloudFormationConfiguration('idindexing', bosslet_config)
    session = bosslet_config.session
    names = bosslet_config.names

    #topic_arn = aws.sns_topic_lookup(session, "ProductionMicronsMailingList")

    role = aws.role_arn_lookup(session, "lambda_cache_execution")
    config.add_arg(Arg.String(
        "LambdaCacheExecutionRole", role,
        "IAM role for " + names.multi_lambda.lambda_))

    def add_lambda(key, name, handler, timeout, memory):
        """A method for defining the common arguments for adding a lambda"""
        config.add_lambda(key,
                          name,
                          Ref('LambdaCacheExecutionRole'),
                          s3=(bosslet_config.LAMBDA_BUCKET,
                              names.multi_lambda.zip,
                              handler),
                          timeout = timeout,
                          memory = memory,
                          runtime='python3.6')

    add_lambda("indexS3WriterLambda",
               names.index_s3_writer.lambda_,
               "write_s3_index_lambda.handler",
               timeout=120, memory=1024)

    add_lambda("indexFanoutIdWriterLambda",
               names.index_fanout_id_writer.lambda_,
               "fanout_write_id_index_lambda.handler",
               timeout=120, memory=256)

    add_lambda("indexWriteIdLambda",
               names.index_write_id.lambda_,
               "write_id_index_lambda.handler",
               timeout=120, memory=512)

    add_lambda("indexWriteFailedLambda",
               names.index_write_failed.lambda_,
               "write_index_failed_lambda.handler",
               timeout=60, memory=128)

    add_lambda("indexFindCuboidsLambda",
               names.index_find_cuboids.lambda_,
               "index_find_cuboids_lambda.handler",
               timeout=120, memory=256)

    add_lambda("indexFanoutEnqueueCuboidsKeysLambda",
               names.index_fanout_enqueue_cuboid_keys.lambda_,
               "fanout_enqueue_cuboid_keys_lambda.handler",
               timeout=120, memory=256)

    add_lambda("indexBatchEnqueueCuboidsLambda",
               names.index_batch_enqueue_cuboids.lambda_,
               "batch_enqueue_cuboids_lambda.handler",
               timeout=60, memory=128)

    add_lambda("startSfnLambda",
               names.start_sfn.lambda_,
               "start_sfn_lambda.handler",
               timeout=60, memory=128)

    add_lambda("indexFanoutDequeueCuboidKeysLambda",
               names.index_fanout_dequeue_cuboid_keys.lambda_,
               "fanout_dequeue_cuboid_keys_lambda.handler",
               timeout=60, memory=128)

    add_lambda("indexDequeueCuboidKeysLambda",
               names.index_dequeue_cuboid_keys.lambda_,
               "dequeue_cuboid_keys_lambda.handler",
               timeout=60, memory=128)

    add_lambda("indexGetNumCuboidKeysMsgsLambda",
               names.index_get_num_cuboid_keys_msgs.lambda_,
               "get_num_msgs_cuboid_keys_queue_lambda.handler",
               timeout=60, memory=128)

    add_lambda("indexCheckForThrottlingLambda",
               names.index_check_for_throttling.lambda_,
               "check_for_index_throttling_lambda.handler",
               timeout=60, memory=128)

    add_lambda("indexInvokeIndexSupervisorLambda",
               names.index_invoke_index_supervisor.lambda_,
               "invoke_index_supervisor_lambda.handler",
               timeout=60, memory=128)

    add_lambda("indexSplitCuboidsLambda",
               names.index_split_cuboids.lambda_,
               "split_cuboids_lambda.handler",
               timeout=120, memory=128)

    add_lambda("indexLoadIdsFromS3Lambda",
               names.index_load_ids_from_s3.lambda_,
               "load_ids_from_s3_lambda.handler",
               timeout=120, memory=128)

    return config


def generate(bosslet_config):
    """Create the configuration and save it to disk."""
    config = create_config(bosslet_config)
    config.generate()


def create(bosslet_config):
    """Create the configuration and launch."""
    if console.confirm("Rebuild multilambda", default = True):
        pre_init(bosslet_config)

    config = create_config(bosslet_config)
    config.create()

    post_init(bosslet_config)


def pre_init(bosslet_config):
    """Build multilambda zip file and put in S3."""
    load_lambdas_on_s3(bosslet_config)


def post_init(bosslet_config):
    """Create step functions."""
    role = 'StatesExecutionRole-us-east-1 '

    for name, path in STEP_FUNCTIONS(bosslet_config):
        sfn.create(bosslet_config, name, path, role)


def post_update(bosslet_config):
    """Create step functions."""

    for name, path in STEP_FUNCTIONS(bosslet_config):
        sfn.update(bosslet_config, name, path)


def update(bosslet_config):
    if console.confirm("Rebuild multilambda", default = True):
        pre_init(bosslet_config)
        update_lambda_code(bosslet_config)

    config = create_config(bosslet_config)
    config.update()

    post_update(bosslet_config)


def delete(bosslet_config):
    CloudFormationConfiguration('idindexing', bosslet_config).delete()
    delete_sfns(bosslet_config)


def delete_sfns(bosslet_config):
    for name, _ in STEP_FUNCTIONS(bosslet_config):
        sfn.delete(bosslet_config, name)


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
from lib import constants as const
from lib import stepfunctions as sfn
from update_lambda_fcn import load_lambdas_on_s3, update_lambda_code

"""
This CloudFormation config file creates the step functions and lambdas used
for annotation (object) id indexing.  When building from scratch, it should
be run after the CloudFormation cachedb config.
"""

def create_config(bosslet_config):
    """Create the CloudFormationConfiguration object."""
    config = CloudFormationConfiguration('idindexing', bosslet_config)
    session = bosslet_config.session
    names = bosslet_config.names

    #topic_arn = aws.sns_topic_lookup(session, "ProductionMicronsMailingList")

    role = aws.role_arn_lookup(session, "lambda_cache_execution")
    config.add_arg(Arg.String(
        "LambdaCacheExecutionRole", role,
        "IAM role for " + names.lambda_.multi_lambda))

    def add_lambda(key, name, handler, timeout, memory):
        """A method for defining the common arguments for adding a lambda"""
        config.add_lambda(key,
                          name,
                          Ref('LambdaCacheExecutionRole'),
                          s3=(bosslet_config.LAMBDA_BUCKET,
                              names.zip.multi_lambda,
                              handler),
                          timeout = timeout,
                          memory = memory,
                          runtime='python3.6')

    add_lambda("indexS3WriterLambda",
               names.lambda_.index_s3_writer,
               "write_s3_index_lambda.handler",
               timeout=120, memory=1024)

    add_lambda("indexFanoutIdWriterLambda",
               names.lambda_.index_fanout_id_writer,
               "fanout_write_id_index_lambda.handler",
               timeout=120, memory=256)

    add_lambda("indexWriteIdLambda",
               names.lambda_.index_write_id,
               "write_id_index_lambda.handler",
               timeout=120, memory=512)

    add_lambda("indexWriteFailedLambda",
               names.lambda_.index_write_failed,
               "write_index_failed_lambda.handler",
               timeout=60, memory=128)

    add_lambda("indexFindCuboidsLambda",
               names.lambda_.index_find_cuboids,
               "index_find_cuboids_lambda.handler",
               timeout=120, memory=256)

    add_lambda("indexFanoutEnqueueCuboidsKeysLambda",
               names.lambda_.index_fanout_enqueue_cuboid_keys,
               "fanout_enqueue_cuboid_keys_lambda.handler",
               timeout=120, memory=256)

    add_lambda("indexBatchEnqueueCuboidsLambda",
               names.lambda_.index_batch_enqueue_cuboids,
               "batch_enqueue_cuboids_lambda.handler",
               timeout=60, memory=128)

    add_lambda("startSfnLambda",
               names.lambda_.start_sfn,
               "start_sfn_lambda.handler",
               timeout=60, memory=128)

    add_lambda("indexFanoutDequeueCuboidKeysLambda",
               names.lambda_.index_fanout_dequeue_cuboid_keys,
               "fanout_dequeue_cuboid_keys_lambda.handler",
               timeout=60, memory=128)

    add_lambda("indexDequeueCuboidKeysLambda",
               names.lambda_.index_dequeue_cuboid_keys,
               "dequeue_cuboid_keys_lambda.handler",
               timeout=60, memory=128)

    add_lambda("indexGetNumCuboidKeysMsgsLambda",
               names.lambda_.index_get_num_cuboid_keys_msgs,
               "get_num_msgs_cuboid_keys_queue_lambda.handler",
               timeout=60, memory=128)

    add_lambda("indexCheckForThrottlingLambda",
               names.lambda_.index_check_for_throttling,
               "check_for_index_throttling_lambda.handler",
               timeout=60, memory=128)

    add_lambda("indexInvokeIndexSupervisorLambda",
               names.lambda_.index_invoke_index_supervisor,
               "invoke_index_supervisor_lambda.handler",
               timeout=60, memory=128)

    add_lambda("indexSplitCuboidsLambda",
               names.lambda_.index_split_cuboids,
               "split_cuboids_lambda.handler",
               timeout=120, memory=128)

    add_lambda("indexLoadIdsFromS3Lambda",
               names.lambda_.index_load_ids_from_s3,
               "load_ids_from_s3_lambda.handler",
               timeout=120, memory=128)

    return config


def generate(bosslet_config):
    """Create the configuration and save it to disk."""
    config = create_config(bosslet_config)
    config.generate()


def create(bosslet_config):
    """Create the configuration and launch."""
    if utils.get_user_confirm("Rebuild multilambda", default = True):
        pre_init(bosslet_config)

    config = create_config(bosslet_config)

    success = config.create()
    if success:
        post_init(bosslet_config)

    return success


def pre_init(bosslet_config):
    """Build multilambda zip file and put in S3."""
    load_lambdas_on_s3(bosslet_config)


def post_init(bosslet_config):
    """Create step functions."""
    names = bosslet_config.names.sfn

    sfn.create(
        bosslet_config, names.index_supervisor,
        'index_supervisor.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(
        bosslet_config, names.index_cuboid_supervisor,
        'index_cuboid_supervisor.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(
        bosslet_config, names.index_id_writer,
        'index_id_writer.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(
        bosslet_config, names.index_find_cuboids,
        'index_find_cuboids.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(
        bosslet_config, names.index_enqueue_cuboids,
        'index_enqueue_cuboids.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(
        bosslet_config, names.index_fanout_enqueue_cuboids,
        'index_fanout_enqueue_cuboids.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(
        bosslet_config, names.index_dequeue_cuboids,
        'index_dequeue_cuboids.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(
        bosslet_config, names.index_fanout_id_writers,
        'index_fanout_id_writers.hsd', 'StatesExecutionRole-us-east-1 ')


def update(bosslet_config):
    if utils.get_user_confirm("Rebuild multilambda", default = True):
        pre_init(bosslet_config)
        update_lambda_code(bosslet_config)

    config = create_config(bosslet_config)
    success = config.update()

    if not success:
        return False

    if utils.get_user_confirm("Replace step functions", default = True):
        delete_sfns(bosslet_config)

        # Need to delay so AWS actually removes the step functions before trying to create them
        delay = 60
        print("Step Functions deleted, waiting for {} seconds".format(delay))
        time.sleep(delay)

        post_init(bosslet_config)

    return True


def delete(bosslet_config):
    CloudFormationConfiguration('idindexing', bosslet_config).delete()
    delete_sfns(bosslet_config)


def delete_sfns(bosslet_config):
    names = bosslet_config.names.sfn
    sfn.delete(bosslet_config, names.index_fanout_id_writers)
    sfn.delete(bosslet_config, names.index_dequeue_cuboids)
    sfn.delete(bosslet_config, names.index_fanout_enqueue_cuboids)
    sfn.delete(bosslet_config, names.index_enqueue_cuboids)
    sfn.delete(bosslet_config, names.index_find_cuboids)
    sfn.delete(bosslet_config, names.index_id_writer)
    sfn.delete(bosslet_config, names.index_cuboid_supervisor)
    sfn.delete(bosslet_config, names.index_supervisor)


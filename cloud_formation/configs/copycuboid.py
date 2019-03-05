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

DEPENDENCIES = []

import json
from lib.cloudformation import CloudFormationConfiguration, Ref, Arn, Arg
from lib.userdata import UserData
from lib import aws
from lib import utils
from lib import constants as const
from lib import stepfunctions as sfn
from lib.lambdas import load_lambdas_on_s3, update_lambda_code

"""
This CloudFormation config file creates resources for copying cuboids from
one channel to another.
"""

def create_config(bosslet_config):
    """Create the CloudFormationConfiguration object."""
    config = CloudFormationConfiguration('copycuboid', bosslet_config)
    names = bosslet_config.names
    session = bosslet_config.session

    role = aws.role_arn_lookup(session, "lambda_cache_execution")
    config.add_arg(Arg.String(
        "LambdaCacheExecutionRole", role,
        "IAM role for multilambda." + domain))

    config.add_sqs_queue(names.copy_cuboid_dlq.sqs, names.copy_cuboid_dlq.sqs, 30, 20160)

    config.add_lambda("CopyCuboidLambda",
                      names.copy_cuboid_lambda.lambda_,
                      Ref("LambdaCacheExecutionRole"),
                      s3=(bosslet_config.LAMBDA_BUCKET,
                          names.multi_lambda.zip,
                          "copy_cuboid_lambda.handler"),
                      timeout=60,
                      memory=128,
                      runtime='python3.6',
                      dlq=Arn(names.copy_cuboid_dlq.sqs))

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
    config.create()


def pre_init(bosslet_config):
    """Build multilambda zip file and put in S3."""
    load_lambdas_on_s3(bosslet_config)


def update(bosslet_config):
    if utils.get_user_confirm("Rebuild multilambda", default = True):
        pre_init(bosslet_config)
        update_lambda_code(bosslet_config)

    config = create_config(bosslet_config)
    config.update()


def delete(bosslet_config):
    config = CloudFormationConfiguration('copycuboid', bosslet_config)
    config.delete()

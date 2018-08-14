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
This CloudFormation config file creates resources for copying cuboids from
one channel to another.
"""

def create_config(session, domain):
    """Create the CloudFormationConfiguration object."""
    config = CloudFormationConfiguration('copycuboid', domain, const.REGION)
    names = AWSNames(domain)

    role = aws.role_arn_lookup(session, "lambda_cache_execution")
    config.add_arg(Arg.String(
        "LambdaCacheExecutionRole", role,
        "IAM role for multilambda." + domain))

    config.add_sqs_queue(names.copy_cuboid_dlq, names.copy_cuboid_dlq, 30, 20160)

    config.add_lambda("CopyCuboidLambda",
                      names.copy_cuboid_lambda,
                      Ref("LambdaCacheExecutionRole"),
                      s3=(aws.get_lambda_s3_bucket(session),
                          "multilambda.{}.zip".format(domain),
                          "copy_cuboid_lambda.handler"),
                      timeout=60,
                      memory=128,
                      runtime='python3.6',
                      dlq=Arn(names.copy_cuboid_dlq))

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
    config.create(session)


def pre_init(session, domain):
    """Build multilambda zip file and put in S3."""
    bucket = aws.get_lambda_s3_bucket(session)
    load_lambdas_on_s3(session, domain, bucket)


def update(session, domain):
    resp = input('Rebuild multilambda: [Y/n]:')
    if len(resp) == 0 or (len(resp) > 0 and resp[0] in ('Y', 'y')):
        pre_init(session, domain)
        bucket = aws.get_lambda_s3_bucket(session)
        update_lambda_code(session, domain, bucket)

    config = create_config(session, domain)
    return config.update(session)


def delete(session, domain):
    CloudFormationConfiguration('copycuboid', domain).delete(session)

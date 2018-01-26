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
from update_lambda_fcn import load_lambdas_on_s3

"""
This CloudFormation config file creates the step functions and lambdas used
for annotation (object) id indexing.  When building from scratch, it should
be run after the CloudFormation cachedb config.
"""

def create_config(session, domain):
    """Create the CloudFormationConfiguration object."""
    config = CloudFormationConfiguration('idindexing', domain, const.REGION)
    names = AWSNames(domain)

    topic_arn = aws.sns_topic_lookup(session, "ProductionMicronsMailingList")

    role = aws.role_arn_lookup(session, "lambda_cache_execution")
    config.add_arg(Arg.String(
        "LambdaCacheExecutionRole", role,
        "IAM role for multilambda." + domain))

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
        session, names.index_cuboid_supervisor_sfn, domain, 
        'index_cuboid_supervisor.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(
        session, names.index_id_writer_sfn, domain, 
        'index_id_writer.hsd', 'StatesExecutionRole-us-east-1 ')


def delete(session, domain):
    names = AWSNames(domain)
    CloudFormationConfiguration('idindexing', domain).delete(session)

    sfn.delete(session, names.index_id_writer_sfn)
    sfn.delete(session, names.index_cuboid_supervisor_sfn)


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

DEPENDENCIES = ['api'] # No actual dependency in config,
                       # but lambda targets DynamoDB tables from api config

"""
Create the DynamoDB lambda configuration which consists of:

  * Lambda function written in NodeJS
  * Lambda policy
"""

import boto3
import configparser
import io
from lib.cloudformation import CloudFormationConfiguration, Arg, Arn, Ref
from lib import aws
from lib import constants as const
from lib import lambdas
import os
import json
import shutil
import subprocess

# Location of repo with the lambda autoscaler.
LAMBDA_ROOT_FOLDER = const.repo_path('cloud_formation', 'lambda', 'dynamodb-lambda-autoscale')

CONFIG_OUTPUT_PATH = os.path.join(LAMBDA_ROOT_FOLDER, 'config.env.production')

CONFIG_INPUT_DIR = const.repo_path('cloud_formation', 'dynamodb-autoscale')
CONFIG_OUTPUT_DIR = os.path.join(LAMBDA_ROOT_FOLDER, 'src', 'configuration')
PROVISIONER_FILENAME = 'BossProvisioners.json'

DYNAMO_LAMBDA_KEY = 'DynamoLambda'
TRIGGER_KEY = 'TriggerDynamoAutoscale'


def create_config(bosslet_config):
    session = bosslet_config.session
    names = bosslet_config.names
    config = CloudFormationConfiguration("dynamolambda", bosslet_config)

    role = aws.role_arn_lookup(session, "lambda_cache_execution")
    config.add_arg(Arg.String("LambdaCacheExecutionRole", role,
                              "IAM role for " + names.multi_lambda.lambda_))

    config.add_lambda(DYNAMO_LAMBDA_KEY,
                      names.dynamo_lambda.lambda_,
                      Ref("LambdaCacheExecutionRole"),
                      handler="index.handler",
                      timeout=120,
                      memory=128,
                      runtime="nodejs8.10",
                      reserved_executions=1)

    config.add_cloudwatch_rule(TRIGGER_KEY,
                               name=names.trigger_dynamo_autoscale.cw,
                               description='Run DynamoDB table autoscaler',
                               targets=[
                                   {
                                       'Arn': Arn(DYNAMO_LAMBDA_KEY),
                                       'Id': names.vault_monitor.lambda_,
                                   }
                               ],
                               schedule='rate(1 minute)',
                               depends_on=[DYNAMO_LAMBDA_KEY])

    config.add_lambda_permission('TriggerPerms',
                                 names.dynamo_lambda.lambda_,
                                 principal='events.amazonaws.com',
                                 source=Arn(TRIGGER_KEY))

    return config


def generate(bosslet_config):
    """Create the configuration and save it to disk"""
    config = create_config(bosslet_config)
    config.generate()


def create(bosslet_config):
    """Create the configuration, and launch it"""
    pre_init(bosslet_config)

    config = create_config(bosslet_config)
    config.create()


def pre_init(bosslet_config):
    """
    Create NodeJS config file from template.  
    Package NodeJS lambda function.
    Upload .zip to S3 bucket.
    """
    write_config_file(bosslet_config)
    copy_provisioners(bosslet_config)

    # Inject the current region into the lambda code
    region_json = const.repo_path('cloud_formation', 'lambda', 'dynamodb-lambda-autoscale', 'src', 'configuration', 'Region.json')
    with open(region_json, 'w') as fh:
        json.dump({'Region': bosslet_config.REGION}, fh)
    
    lambdas.load_lambdas_on_s3(bosslet_config,
                               bosslet_config.names.dynamo_lambda.lambda_,)


def write_config_file(bosslet_config):
    """Create the configuration file with environmental variables
    for the lambda

    Args:
        bosslet_config (BossConfiguration): Bosslet where the lambda will be deployed
    """
    config_lines = []

    config_lines.append('VPC_DOMAIN = {}'.format(bosslet_config.INTERNAL_DOMAIN))

    val =  bosslet_config.SLACK_WEBHOOK_PATH_DYNAMODB_AUTOSCALE
    if val:
        host = bosslet_config.SLACK_WEBHOOK_HOST
        print('\nWill post to Slack at https://{}{}'.format(host, val))

        config_lines.append('SLACK_WEBHOOK_HOST = "{}"'.format(host))
        config_lines.append('SLACK_WEBHOOK_PATH = "{}"'.format(val))

    # if production.boss = prod path
    # if * = prod path
    #   if != integration.boss = BossDefaultProvisioners

    config = "\n".join(config_lines)

    with open(CONFIG_OUTPUT_PATH, 'w') as out:
        out.write(config)


def copy_provisioners(bosslet_config):
    """Copy the lambda's provisioner configuration files into the lambda code
    directory so they are included in the build process

    Args:
        bosslet_config (BossConfiguration): Bosslet where the lambda will be deployed
    """
    filename = "BossTableConfig.json"
    src = os.path.join(CONFIG_INPUT_DIR, filename)
    dst = os.path.join(CONFIG_OUTPUT_DIR, filename)
    shutil.copy(src, dst)

    filename = "{}.json".format(bosslet_config.DYNAMODB_AUTOSCALE_PROVISIONER)
    src = os.path.join(CONFIG_INPUT_DIR, filename)
    dst = os.path.join(CONFIG_OUTPUT_DIR, PROVISIONER_FILENAME)
    shutil.copy(src, dst)

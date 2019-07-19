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
import os
import shutil
import subprocess

# Location of repo with the lambda autoscaler.
LAMBDA_ROOT_FOLDER = const.repo_path('cloud_formation', 'lambda', 'dynamodb-lambda-autoscale')

# Zip file created by `npm run build`
LAMBDA_ZIP_FILE = os.path.join(LAMBDA_ROOT_FOLDER, 'dist.zip')

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

    lambda_key = bosslet_config.names.dynamodb_autoscale.zip
    config.add_lambda(DYNAMO_LAMBDA_KEY,
                      names.dynamo_lambda.lambda_,
                      Ref("LambdaCacheExecutionRole"),
                      s3=(bosslet_config.LAMBDA_BUCKET,
                          lambda_key,
                          "index.handler"),
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
    
    build_lambda(bosslet_config)

    zip_file = os.path.join(LAMBDA_ROOT_FOLDER, LAMBDA_ZIP_FILE)
    zips_s3_key = upload_to_s3(bosslet_config, zip_file)


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


def build_lambda(bosslet_config):
    """Package lambda in preparation to upload to S3."""
    install_node_deps()
    build_node(bosslet_config)


def install_node_deps():
    """npm install NodeJS dependencies."""
    print('Installing NodeJS dependencies.')
    args = ('npm', 'install')
    popen = subprocess.Popen(args, cwd=LAMBDA_ROOT_FOLDER, stdout=subprocess.PIPE)
    exit_code = popen.wait()
    output = popen.stdout.read()
    if not exit_code == 0:
        print(str(output))
        raise RuntimeError('Failed to install dependencies.')


def build_node(bosslet_config):
    """Build and package in dist.zip."""
    print('Packaging NodeJS app.')

    # Inject the current region into the lambda code
    region_json = const.repo_path('cloud_formation', 'lambda', 'dynamodb-lambda-autoscale', 'src', 'configuration', 'Region.json')
    with open(region_json, 'w') as fh:
        json.dump({'Region': bosslet_config.REGION}, fh)

    args = ('npm', 'run', 'build')
    # Use env vars to pass credentials / region instead of as arguments to build call
    env = os.environ.copy()
    env['AWS_PROFILE'] = bosslet_config.PROFILE
    env['AWS_REGION'] = bosslet_config.REGION
    popen = subprocess.Popen(args, cwd=LAMBDA_ROOT_FOLDER, env=env, stdout=subprocess.PIPE)
    exit_code = popen.wait()
    output = popen.stdout.read()
    if not exit_code == 0:
        print(str(output))
        raise RuntimeError('Failed to build Node application.')


def upload_to_s3(bosslet_config, zip_file):
    """Upload the zip file to the correct S3 bucket.

    Args:
        bosslet_config (BossConfiguration): Bosslet configuration class which contains everything specific to a boss:
                                            session, bucket, names
        zip_file (str): Name of zip file.

    """
    print('Uploading to S3.')
    bucket = bosslet_config.LAMBDA_BUCKET
    session = bosslet_config.session
    key = bosslet_config.names.dynamodb_autoscale.zip
    s3 = session.client('s3')

    try:
        s3.create_bucket(Bucket=bucket)
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass # Only us-east-1 will not throw an exception if the bucket already exists

    s3.put_object(Bucket=bucket, Key=key, Body=open(zip_file, 'rb'))


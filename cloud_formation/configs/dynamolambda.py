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
import subprocess

# Location of repo with the lambda autoscaler.
LAMBDA_ROOT_FOLDER = const.repo_path('cloud_formation', 'lambda', 'dynamodb-lambda-autoscale')

# Zip file created by `npm run build`
LAMBDA_ZIP_FILE = os.path.join(LAMBDA_ROOT_FOLDER, 'dist.zip')

CONFIG_TEMPLATE_PATH = const.repo_path('cloud_formation', 'configs', 'dynamo_config.template')
CONFIG_OUTPUT_PATH = os.path.join(LAMBDA_ROOT_FOLDER, 'config.env.production')

DYNAMO_LAMBDA_KEY = 'DynamoLambda'
TRIGGER_KEY = 'TriggerDynamoAutoscale'

SLACK_WEBHOOK_HOST = 'SLACK_WEBHOOK_HOST'

# This variable is the one used by the lambda function.
SLACK_WEBHOOK_PATH = 'SLACK_WEBHOOK_PATH'

# Value in this config variable will be written to SLACK_WEBHOOK_PATH when
# standing up the service in production.
SLACK_WEBHOOK_PATH_PRODUCTION = 'SLACK_WEBHOOK_PATH_PRODUCTION'

# Value in this config variable will be written to SLACK_WEBHOOK_PATH when
# standing up the service in a development stack or an integration stack.
SLACK_WEBHOOK_PATH_DEV = 'SLACK_WEBHOOK_PATH_DEV'

# Domain name will be included in messages to Slack and also determines
# whether SLACK_WEBHOOK_PATH_DEV's or SLACK_WEBHOOK_PATH_PRODUCTION's value is 
# written to SLACK_WEBHOOK_PATH.
VPC_DOMAIN = 'VPC_DOMAIN'

# Used to override normal autoscale rules when creating a developer's stack.
# All tables will use the autoscale rules defined by the "default" config to
# avoid spending too much.  The production autoscale rules have minimums that
# are way too high for DynamoDB tables for developers.
DEV_STACK = 'DEV_STACK'


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
    with open(CONFIG_TEMPLATE_PATH) as fh:
        config_str = fh.read()
    update_config_file(config_str, bosslet_config)
    
    build_lambda()
    zip_file = os.path.join(LAMBDA_ROOT_FOLDER, LAMBDA_ZIP_FILE)
    zips_s3_key = upload_to_s3(bosslet_config, zip_file)


def update_config_file(config_str, bosslet_config):
    """Update config file that stores environment variables for the lambda
    environment.

    Args:
        config_str (str): String representation of config file template.
    """
    parser = configparser.ConfigParser()
    # Disable default transform to lowercase of keys.
    parser.optionxform = lambda option: option
    parser.read_string(config_str)
    parser.set('default', VPC_DOMAIN, bosslet_config.INTERNAL_DOMAIN)

    #raise Exception("Need to remove logic for dev vs production setup")
    # TODO: remove logic for dev vs production setup
    # TODO: figure out how to handle SLACK integration, as not everyone will use it
    slack_host = parser.get('default', SLACK_WEBHOOK_HOST)
    slack_path_prod = parser.get('default', SLACK_WEBHOOK_PATH_PRODUCTION)
    slack_path_dev = parser.get('default', SLACK_WEBHOOK_PATH_DEV)
    session = bosslet_config.session
    domain = bosslet_config.INTERNAL_DOMAIN
    if domain == 'production.boss':
        parser.set('default', SLACK_WEBHOOK_PATH, slack_path_prod)
    else:
        parser.set('default', SLACK_WEBHOOK_PATH, slack_path_dev)
        if domain != 'integration.boss':
            # Override normal autoscale parameters when deploying to a
            # developer stack.
            parser.set('default', DEV_STACK, '')
    slack_path = parser.get('default', SLACK_WEBHOOK_PATH)

    # Remove stack specific variables before outputting.
    parser.remove_option('default', SLACK_WEBHOOK_PATH_DEV)
    parser.remove_option('default', SLACK_WEBHOOK_PATH_PRODUCTION)

    print('\nWill post to Slack at https://{}{}'.format(slack_host, slack_path))

    updated_config = io.StringIO()
    parser.write(updated_config)
    config_str = updated_config.getvalue()
    updated_config.close()

    # Strip default section header from config.  NodeJS config file does not
    # use sections.
    _, headerless_config = config_str.split('[default]', 1)

    # Convert variable names back to upper case.
    headerless_config = headerless_config.replace(
        SLACK_WEBHOOK_HOST.lower(), SLACK_WEBHOOK_HOST).replace(
            SLACK_WEBHOOK_PATH.lower(), SLACK_WEBHOOK_PATH).replace(
                VPC_DOMAIN.lower(), VPC_DOMAIN)

    with open(CONFIG_OUTPUT_PATH, 'w') as out:
        out.write(headerless_config)
    # print(headerless_config)


def build_lambda():
    """Package lambda in preparation to upload to S3."""
    install_node_deps()
    build_node()


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


def build_node():
    """Build and package in dist.zip."""
    print('Packaging NodeJS app.')
    args = ('npm', 'run', 'build')
    popen = subprocess.Popen(args, cwd=LAMBDA_ROOT_FOLDER, stdout=subprocess.PIPE)
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


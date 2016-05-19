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

"""A driver script for creating AWS CloudFormation Stacks."""

import argparse
import sys
import os
import importlib
from boto3.session import Session
from botocore.exceptions import ClientError
import json
import pprint
import glob
import time
import library as lib

import hosts

"""
create vpc.boss vpc
create subnet.vpc.boss subnet
create subnet.vpc.boss instance
"""

def create_session(credentials):
    """Read the AWS from the credentials dictionary and then create a boto3
    connection to AWS with those credentials.
    """
    session = Session(aws_access_key_id = credentials["aws_access_key"],
                      aws_secret_access_key = credentials["aws_secret_key"],
                      region_name = 'us-east-1')
    return session

def create_config(session, domain, config):
    """Import 'configs.<config>' and then call the create() function with
    <session> and <domain>.
    """
    module = importlib.import_module("configs." + config)
    module.create(session, domain)

def delete_config(session, domain, config):
    """Deletes the given stack from CloudFormation.

    Initiates the stack delete and waits for it to finish.  config and domain
    are combined to identify the stack.

    Args:
        session (boto3.Session): An active session.
        domain (string): Name of domain.
        config (string): Name of config.

    Returns:
        (bool) : True if stack successfully deleted.
    """
    name = lib.domain_to_stackname(config + "." + domain)
    client = session.client("cloudformation")
    client.delete_stack(StackName = name)
    # waiter = client.get_waiter('stack_delete_complete')
    # waiter.wait(StackName = name)

    print("Waiting for delete ", end="", flush=True)

    try:
        response = client.describe_stacks(StackName = name)
        get_status = lambda r: r['Stacks'][0]['StackStatus']
        while get_status(response) == 'DELETE_IN_PROGRESS':
            time.sleep(5)
            print(".", end="", flush=True)
            response = client.describe_stacks(StackName=name)
        print(" done")

        if get_status(response) == 'DELETE_COMPLETE':
            print("Deleted stack '{}'".format(name))
            return True

        print("Status of stack '{}' is '{}'".format(name, get_status(response)))
        return False
    except ClientError as e:
        # Stack doesn't exist or no longer exists.
        print(" done")

    return True

def generate_config(domain, config):
    """Import 'configs.<config>' and then call the generate() function with
    'templates' directory and <domain>.
    """
    module = importlib.import_module("configs." + config)
    module.generate("templates", domain)

def post_init(session, domain, config):
    """Import 'configs.<config>' and then call the create() function with
    <session> and <domain>.
    """
    module = importlib.import_module("configs." + config)
    if "post_init" in dir(module):
        module.post_init(session, domain)

if __name__ == '__main__':
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    config_names = [x.split('/')[1].split('.')[0] for x in glob.glob("configs/*.py") if "__init__" not in x]
    config_help = create_help("config_name supports the following:", config_names)

    actions = ["create", "generate", "delete", "post-init"]
    actions_help = create_help("action supports the following:", actions)

    scenarios = ["development", "production"]
    scenario_help = create_help("scenario supports the following:", scenarios)

    parser = argparse.ArgumentParser(description = "Script the creation and provisioning of CloudFormation Stacks",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=actions_help + config_help + scenario_help)
    parser.add_argument("--aws-credentials", "-a",
                        metavar = "<file>",
                        default = os.environ.get("AWS_CREDENTIALS"),
                        type = argparse.FileType('r'),
                        help = "File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("--ami-version",
                        metavar = "<ami-version>",
                        default = "latest",
                        help = "The AMI version to use when selecting images (default: latest)")
    parser.add_argument("--scenario",
                        metavar = "<scenario>",
                        default = "development",
                        choices = scenarios,
                        help = "The deployment configuration to use when creating the stack (instance size, autoscale group size, etc) (default: development)")
    parser.add_argument("action",
                        choices = actions,
                        metavar = "action",
                        help = "Action to execute")
    parser.add_argument("domain_name", help="Domain in which to execute the configuration (example: subnet.vpc.boss)")
    parser.add_argument("config_name",
                        choices = config_names,
                        metavar = "config_name",
                        help="Configuration to act upon (imported from configs/)")

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    os.environ["AMI_VERSION"] = args.ami_version
    os.environ["SCENARIO"] = args.scenario

    credentials = json.load(args.aws_credentials)

    session = create_session(credentials)

    if args.action in ("create", ):
        create_config(session, args.domain_name, args.config_name)
    elif args.action in ("post-init", ):
        post_init(session, args.domain_name, args.config_name)
    elif args.action in ("generate", "gen"):
        generate_config(args.domain_name, args.config_name)
    elif args.action in ("delete", "del"):
        if not delete_config(session, args.domain_name, args.config_name):
            sys.exit(1)

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
import json
import pprint
import glob
import time
import library as lib

import hosts

# Add a reference to boss-manage/lib/ so that we can import those files
cur_dir = os.path.dirname(os.path.realpath(__file__))
lib_dir = os.path.normpath(os.path.join(cur_dir, "..", "lib"))
sys.path.append(lib_dir)
import exceptions

def create_session(credentials):
    """Read the AWS from the credentials dictionary and then create a boto3
    connection to AWS with those credentials.
    """
    session = Session(aws_access_key_id = credentials["aws_access_key"],
                      aws_secret_access_key = credentials["aws_secret_key"],
                      region_name = 'us-east-1')
    return session

def build_dispatch(module, config):
    """Build a dispatch dictionary of the different supported methods. Fill in the
    default implementation if none is given (if supported).

    could use module.__dict__.get(method)
    """
    dispatch = {}
    dispatch['create'] = module.create if hasattr(module, 'create') else None
    dispatch['update'] = module.update if hasattr(module, 'update') else None
    dispatch['delete'] = module.delete if hasattr(module, 'delete') else lambda s,d: lib.delete_stack(s, d, config)
    dispatch['post_init'] = module.post_init if hasattr(module, 'post_init') else None
    dispatch['pre_init'] = module.pre_init if hasattr(module, 'pre_init') else None

    dispatch['generate'] = lambda s,d: module.generate("templates", d) if hasattr(module, 'generate') else None

    return dispatch

def call_config(session, domain, config, func_name):
    """Import 'configs.<config>' and then call the requested function with
    <session> and <domain>.
    """
    module = importlib.import_module("configs." + config)

    func = build_dispatch(module, config).get(func_name)
    if func is None:
        print("Configuration '{}' doesn't implement function '{}'".format(config, func_name))
    else:
        func(session, domain)

if __name__ == '__main__':
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    config_names = [x.split('/')[1].split('.')[0] for x in glob.glob("configs/*.py") if "__init__" not in x]
    config_help = create_help("config_name supports the following:", config_names)

    actions = ["create", "update", "delete", "post-init", "pre-init", "generate"]
    actions_help = create_help("action supports the following:", actions)

    scenarios = ["development", "production", "ha-development"]
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

    try:
        func = args.action.replace('-','_')
        ret = call_config(session, args.domain_name, args.config_name, func)
        if ret == False:
            sys.exit(1)
    except exceptions.StatusCheckError as ex:
        target = 'the server'
        if hasattr(ex, 'target') and ex.target is not None:
            target = ex.target

        print()
        print(ex)
        print("Check networking and {}".format(target))
        print("Then run the following command:")
        print("\t" + lib.get_command("post-init"))
    except exceptions.KeyCloakLoginError as ex:
        print()
        print(ex)
        print("Check Vault and Keycloak")
        print("Then run the following command:")
        print("\t" + lib.get_command("post-init"))
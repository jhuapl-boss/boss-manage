#!/usr/bin/env python3

"""A driver script for creating AWS CloudFormation Stacks."""

import argparse
import sys
import os
import importlib
from boto3.session import Session
import json
import pprint
import glob

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

def generate_config(domain, config):
    """Import 'configs.<config>' and then call the generate() function with
    'templates' directory and <domain>.
    """
    module = importlib.import_module("configs." + config)
    module.generate("templates", domain)

if __name__ == '__main__':
    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    config_names = [x.split('/')[1].split('.')[0] for x in glob.glob("configs/*.py") if "__init__" not in x]
    config_help = create_help("config_name supports the following:", config_names)

    actions = ["create", "generate"]
    actions_help = create_help("action supports the following:", actions)

    parser = argparse.ArgumentParser(description = "Script the creation and provisioning of CloudFormation Stacks",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=actions_help + config_help)
    parser.add_argument("--aws-credentials", "-a",
                        metavar = "<file>",
                        default = os.environ.get("AWS_CREDENTIALS"),
                        type = argparse.FileType('r'),
                        help = "File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("--ami-version",
                        metavar = "<ami-version>",
                        default = "latest",
                        help = "The AMI version to use when selecting images (default: latest)")
    parser.add_argument("action",
                        choices = ["create","generate"],
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

    credentials = json.load(args.aws_credentials)

    session = create_session(credentials)

    if args.action in ("create", ):
        create_config(session, args.domain_name, args.config_name)
    elif args.action in ("generate", "gen"):
        generate_config(args.domain_name, args.config_name)

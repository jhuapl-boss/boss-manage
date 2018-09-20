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

"""A script to create all necessary aws resources to automatically build a development test stack
from the latest ami's and perform all possible unit tests. Takes in user e-mail to which SNS
sends a message daily reporting passed and failed tests."""

import argparse
import sys
import os
import importlib
import glob

import alter_path
from lib import exceptions
from lib import aws
from lib import utils
from lib.cloudformation import CloudFormationConfiguration
from lib.stepfunctions import heaviside

if __name__ == '__main__':

    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    config_names = [x.split('/')[1].split('.')[0] for x in glob.glob("configs/*.py") if "__init__" not in x]
    config_help = create_help("config_name supports the following:", config_names)

    parser = argparse.ArgumentParser(description = "Script the creation and provisioning of CloudFormation Stacks",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=actions_help)
    parser.add_argument("--aws-credentials", "-a",
                        metavar = "<file>",
                        default = os.environ.get("AWS_CREDENTIALS"),
                        type = argparse.FileType('r'),
                        help = "File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("email",
                        metavar = "email",
                        help = "email to send messages to")
    parser.add_argument("--internal",
                        action = "store_true",
                        help="Attemps to execute cloudformation script without any credentials. Meant to use from internal aws instances")

    args = parser.parse_args()

    if args.internal:
        session = aws.use_iam_role()

    else:
        if args.aws_credentials is None:
            parser.print_usage()
            print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
            sys.exit(1)
        session = aws.create_session(args.aws_credentials)

    ec2 = session.client('ec2')

    # Create aa security group for the buil ec2 instance to use. 
    sec_group = ec2.create_security_group(GroupName='test_env', Description='Temporary security group')
    sec_group_id = sec_group['GroupId']
    
    data = EC2.authorize_security_group_ingress(
        GroupId=sec_group_id,
        IpPermissions=[
            {'IpProtocol': 'tcp',
            'FromPort': 22,
            'ToPort':22,
            'IpRanges':[({'CidrIp': '52.3.13.189/32'})]} #Make bastion IP a variable.
        ]
    )
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

"""
Script will copy the AMIs - This is useful at the end of a sprint when you want to make
AMIs to with the sprint name.
"""

import argparse
import sys
import os
import pprint
import traceback

import alter_path
from lib import aws
from lib import hosts
from lib.names import AWSNames

AMIS = ["endpoint.boss", "cachemanager.boss", "proofreader-web.boss", "auth.boss", "vault.boss", "consul.boss", "activities.boss"]


def copy_amis(session, ami_ending, new_ami_ending):
    """
    changes Route53 entry for the api in domain to use cloudfront for the s3 maintenance bucket.
    Args:
        session(Session): boto3 session object
        ami_ending(str): short hash attached to AMIs to copy from
        new_ami_ending(str): new post_name to assign AMI copies.

    Returns:
        Nothing
    """
    client = session.client("ec2")
    for prefix in AMIS:
        (ami_id, hash) = aws.ami_lookup(session, prefix, version=ami_ending)
        print(str(ami_id))
        try:
            response = client.copy_image(SourceRegion=session.region_name,
                                         SourceImageId=ami_id,
                                         Name=prefix + "-" + new_ami_ending,
                                         Description="Copied from ami id {}".format(ami_id))
            pprint.pprint(response)
        except:
            traceback.print_exc()



cmd_help = "this will copy all AMIs given a specific version or name to a new AMI name, like sprint01."



def create_parser():
    """
    Creates the argumentPaser
    Returns:
        (ArgumentParser) not yet parsed.
    """
    parser = argparse.ArgumentParser(
        description="",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=cmd_help)
    parser.add_argument("--aws-credentials", "-a",
                        metavar="<file>",
                        default=os.environ.get("AWS_CREDENTIALS"),
                        type=argparse.FileType('r'),
                        help="File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("ami_ending",
                        help="ami_ending ex: hc1ea3281 or latest")
    parser.add_argument("new_ami_ending",
                        help="new ami ending like: sprint01")

    return parser


if __name__ == '__main__':
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    parser = create_parser()
    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    session = aws.create_session(args.aws_credentials)
    copy_amis(session, args.ami_ending, args.new_ami_ending)


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
from lib import configuration
from lib.names import AWSNames

# TODO: Just read the packer config variables files
AMIS = ["endpoint",
        "cachemanager",
        "proofreader-web",
        "auth",
        "vault",
        "consul",
        "activities"]


def copy_amis(bosslet_config, ami_ending, new_ami_ending):
    """
    changes Route53 entry for the api in domain to use cloudfront for the s3 maintenance bucket.
    Args:
        session(Session): boto3 session object
        ami_ending(str): short hash attached to AMIs to copy from
        new_ami_ending(str): new post_name to assign AMI copies.

    Returns:
        Nothing
    """
    client = bosslet_config.session.client("ec2")
    for prefix in AMIS:
        prefix += bosslet_config.AMI_SUFFIX
        (ami_id, hash) = aws.ami_lookup(session, prefix, version=ami_ending)
        print(str(ami_id))
        try:
            response = client.copy_image(SourceRegion=bosslet_config.REGION,
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
    parser.add_argument("bosslet_name",
                        help="Bosslet in which to execute the configuration")
    parser.add_argument("ami_ending",
                        help="ami_ending ex: hc1ea3281 or latest")
    parser.add_argument("new_ami_ending",
                        help="new ami ending like: sprint01")

    return parser


if __name__ == '__main__':
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    parser = create_parser()
    args = parser.parse_args()

    if not configuration.valid_bosslet(args.bosslet_name):
        parser.print_usage()
        print("Error: Bosslet name '{}' doesn't exist in configs file ({})".format(args.bosslet_name, configuration.CONFIGS_PATH))
        sys.exit(1)

    bosslet_config = configuration.BossConfiguration(args.bosslet_name)
    copy_amis(bosslet_config, args.ami_ending, args.new_ami_ending)


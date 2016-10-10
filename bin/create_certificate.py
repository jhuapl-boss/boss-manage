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
"""A script to create a certificate request in AWS Certificate Manager"""

import argparse
import sys
import os
from boto3.session import Session
import json

# Add a reference to boss-manage/cloud_formation/ so that we can import those files
cur_dir = os.path.dirname(os.path.realpath(__file__))
cf_dir = os.path.normpath(os.path.join(cur_dir, "..", "cloud_formation"))
sys.path.append(cf_dir)
import library as lib


def create_session(credentials):
    """
    Read the AWS from the credentials dictionary and then create a boto3
    connection to AWS with those credentials.
    Args:
        credentials: AWS credentials in JSON format

    Returns: results boto3 AWS session object

    """
    session = Session(aws_access_key_id=credentials["aws_access_key"],
                      aws_secret_access_key=credentials["aws_secret_key"],
                      region_name='us-east-1')
    return session


if __name__ == '__main__':
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    parser = argparse.ArgumentParser(description="Request SSL domain certificates for theboss.io subdomains",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog='create domain cert')
    parser.add_argument("--aws-credentials", "-a",
                        metavar="<file>",
                        default=os.environ.get("AWS_CREDENTIALS"),
                        type=argparse.FileType('r'),
                        help="File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("domain_name", help="Domain to create the SSL certificate for (Ex: api.integration.theboss.io)")

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    credentials = json.load(args.aws_credentials)
    session = create_session(credentials)

    results = lib.request_cert(session, args.domain_name, lib.get_hosted_zone(session))
    print(results)

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

import alter_path
from lib import aws

if __name__ == '__main__':
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    # DP NOTE: This should possibly be in user-scratch as it is specific to our deployment
    # DP ???: Still used?
    parser = argparse.ArgumentParser(description="Request SSL domain certificates for theboss.io subdomains",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog='create domain cert')
    parser.add_argument("domain_name", help="Domain to create the SSL certificate for (Ex: api.integration.theboss.io)")

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    session = aws.create_session(args.aws_credentials)

    results = aws.request_cert(session, args.domain_name, aws.get_hosted_zone(session))
    print(results)

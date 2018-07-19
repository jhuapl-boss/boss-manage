#!/usr/bin/env python3

# Copyright 2018 The Johns Hopkins University Applied Physics Laboratory
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

import argparse
import sys
import os
import getpass
import botocore

import alter_path
from lib import aws

def read_password():
    while True:
        initial = getpass.getpass()
        confirm = getpass.getpass('Verify: ')
        if initial == confirm:
            return initial
        else:
            print("Passwords don't match")
            print()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = "Script to reset the password for an IAM user")
    parser.add_argument("--aws-credentials", "-a",
                        metavar = "<file>",
                        default = os.environ.get("AWS_CREDENTIALS"),
                        type = argparse.FileType('r'),
                        help = "File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("--disable-reset",
                        action = "store_true",
                        help = "Disable the need to reset the password on next login")
    parser.add_argument("iam_user", help="Name of the IAM User account")

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    session = aws.create_session(args.aws_credentials)
    iam = session.resource('iam')
    profile = iam.LoginProfile(args.iam_user)

    try:
        profile.create_date
    except iam.meta.client.exceptions.NoSuchEntityException:
        print("User doesn't exist")
        sys.exit(1)

    profile.update(Password = read_password(),
                   PasswordResetRequired = not args.disable_reset)


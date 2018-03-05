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
Tell a lambda to reload its code from S3.  

Useful when developing and small changes need to be made to a lambda function, 
but a full rebuild of the entire zip file isn't required.
"""

import alter_path
import argparse
import boto3
from lib import aws
import os
import sys

def freshen_lambda(session, domain, lambda_name, bucket):
    zip_name = 'multilambda.{}.zip'.format(domain)
    full_name = add_domain_name(lambda_name, domain)
    client = session.client('lambda')
    resp = client.update_function_code(
        FunctionName=full_name,
        S3Bucket=bucket,
        S3Key=zip_name,
        Publish=True)
    print(resp)


def add_domain_name(lambda_name, domain):
    full_name = '{}.{}'.format(lambda_name, domain)
    return full_name.replace('.', '-')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Script for freshening lambda function code from S3. ' + 
        'To supply arguments from a file, provide the filename prepended with an `@`.',
        fromfile_prefix_chars = '@')
    parser.add_argument(
        '--aws-credentials', '-a',
        metavar='<file>',
        default=os.environ.get('AWS_CREDENTIALS'),
        type=argparse.FileType('r'),
        help='File with credentials for connecting to AWS (default: AWS_CREDENTIALS)')
    parser.add_argument(
        'domain',
        help='Domain that lambda functions live in, such as integration.boss.')
    parser.add_argument(
        'lambda_name',
        help='Name of lambda function to freshen.')

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print('Error: AWS credentials not provided and AWS_CREDENTIALS is not defined')
        sys.exit(1)

    session = aws.create_session(args.aws_credentials)
    bucket = aws.get_lambda_s3_bucket(session)

    freshen_lambda(session, args.domain, args.lambda_name, bucket)


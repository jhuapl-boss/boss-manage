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
Upload a  multilambda.domain.zip to the S3 bucket.  Useful when
developing and small changes need to be made to a lambda function, but a full
rebuild of the entire zip file isn't required.
"""

import alter_path
import argparse
import boto3
from lib import aws
import os
import sys

def upload_lambda_zip(session, domain, path, bucket):
    s3 = session.client('s3')
    zip_name = 'multilambda.{}.zip'.format(domain)
    with open(path, 'rb') as in_file:
        resp = s3.put_object(Bucket=bucket, Key=zip_name, Body=in_file)
    print(resp)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Script for downloading lambda function code from S3. ' + 
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
        'zip_name',
        help='Name of zip file to upload to S3.')

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print('Error: AWS credentials not provided and AWS_CREDENTIALS is not defined')
        sys.exit(1)

    session = aws.create_session(args.aws_credentials)
    bucket = aws.get_lambda_s3_bucket(session)

    upload_lambda_zip(session, args.domain, args.zip_name, bucket)


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

import os
import sys

import alter_path
from lib import aws
from lib import configuration

def freshen_lambda(bosslet_config, lambda_name):
    zip_name = bosslet_config.names.multi_lambda.zip
    full_name = bosslet_config.names[lambda_name].lambda_
    client = bosslet_config.session.client('lambda')
    resp = client.update_function_code(
        FunctionName=full_name,
        S3Bucket=bosslet_config.LAMBDA_BUCKET,
        S3Key=zip_name,
        Publish=True)
    print(resp)


if __name__ == '__main__':
    parser = configuration.BossParser(description = "Script for freshening lambda " +
                                      "function code from S3. To supply arguments " +
                                      "from a file, provide the filename prepended " +
                                      "with an '@'",
                                      fromfile_prefix_chars = '@')
    parser.add_bosslet()
    parser.add_argument('lambda_name',
                        help='Name of lambda function to freshen.')

    args = parser.parse_args()

    freshen_lambda(args.bosslet_config, args.lambda_name)


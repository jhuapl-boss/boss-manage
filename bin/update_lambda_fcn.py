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
Update an existing lambda function.  Note, that the lambda handler function
is not changed.

load_lambdas_on_s3() zips spdb, bossutils, lambda, and lambda_utils as found
in boss-manage's submodules and places it on the lambda build server.  Next,
makedomainenv is run on the lambda build server to create the virtualenv for
the lambda function.  Finally, the virutalenv is zipped and uploaded to S3.

update_lambda_code() tells AWS to point the existing lambda function at the
new zip in S3.
"""
import alter_path
from lib import configuration
from lib.lambdas import load_lambdas_on_s3, update_lambda_code

if __name__ == '__main__':
    parser = configuration.BossParser(description='Script for updating lambda function code. ' + 
                                      'To supply arguments from a file, provide the filename prepended with an `@`.',
                                      fromfile_prefix_chars = '@')
    parser.add_bosslet()

    args = parser.parse_args()

    load_lambdas_on_s3(args.bosslet_config)
    update_lambda_code(args.bosslet_config)

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

import argparse
import boto3
import configuration
import library as lib
import os
import shlex
import sys
import tempfile

cur_dir = os.path.dirname(os.path.realpath(__file__))
vault_dir = os.path.normpath(os.path.join(cur_dir, "..", "vault"))
sys.path.append(vault_dir)
import bastion
from ssh import *

# Server used to build spdb and assemble the final lambda zip file.
LAMBDA_BUILD_SERVER = "52.23.27.39"

AWS_REGION = 'us-east-1'

# Name that is prepended to the domain name (periods are replaced with dashes).
LAMBDA_PREFIX = 'multiLambda-'

# Bucket that stores all of our lambda functions.
S3_BUCKET = 'boss-lambda-env'

def get_lambda_name(domain):
    """Get the name of the lambda function as known to AWS.

    Args:
        domain (string): The VPC's domain name such as integration.boss.

    Returns:
        (string)
    """
    return LAMBDA_PREFIX + domain.replace('.', '-')

def get_lambda_zip_name(domain):
    """Get name of zip file containing lambda.

    This must match the name created in the makedomainenv script that runs on
    the lambda build server.

    Args:
        domain (string): The VPC's domain name such as integration.boss.

    Returns:
        (string)
    """
    return 'multilambda.{}.zip'.format(domain)

def update_lambda_code(session, domain):
    client = session.client('lambda')
    resp = client.update_function_code(
        FunctionName=get_lambda_name(domain),
        S3Bucket=S3_BUCKET,
        S3Key=get_lambda_zip_name(domain),
        Publish=True)
    print(resp)

def load_lambdas_on_s3(domain):
    """Zip up spdb, bossutils, lambda and lambda_utils.  Upload to S3.

    Uses the lambda build server (an Amazon Linux AMI) to compile C code and
    prepare the virtualenv that's ultimately contained in the zip file placed
    in S3.

    Args:
        domain (string): The VPC's domain name such as integration.boss.
    """
    tempname = tempfile.NamedTemporaryFile(delete=True)
    zipname = tempname.name + '.zip'
    tempname.close()
    print('Using temp zip file: ' + zipname)
    cwd = os.getcwd()
    os.chdir('../salt_stack/salt/spdb/files')
    lib.write_to_zip('spdb.git', zipname, False)
    os.chdir(cwd)
    os.chdir('../salt_stack/salt/boss-tools/files/boss-tools.git')
    lib.write_to_zip('bossutils', zipname)
    lib.write_to_zip('lambda', zipname)
    lib.write_to_zip('lambdautils', zipname)

    os.chdir(cwd)
    os.chdir('../salt_stack/salt/ndingest/files')
    lib.write_to_zip('ndingest.git', zipname)

    # Restore original working directory.
    os.chdir(cwd)

    print("Copying local modules to lambda-build-server")

    #copy the zip file to lambda_build_server
    apl_bastion_ip = os.environ.get("BASTION_IP")
    apl_bastion_key = os.environ.get("BASTION_KEY")
    apl_bastion_user = os.environ.get("BASTION_USER")
    local_port = bastion.locate_port()
    proc = bastion.create_tunnel(apl_bastion_key, local_port, LAMBDA_BUILD_SERVER, 22, apl_bastion_ip, bastion_user="ubuntu")

    # Note: using bastion key as identity for scp.
    scp_cmd = "scp -i {} -P {} {} {} ec2-user@localhost:sitezips/{}".format(
        apl_bastion_key,
        local_port,
        bastion.SSH_OPTIONS,
        zipname,
        domain + ".zip")

    try:
        return_code = subprocess.call(shlex.split(scp_cmd))  # close_fds=True, preexec_fn=bastion.become_tty_fg
        print("scp return code: " + str(return_code))
    finally:
        proc.terminate()
        proc.wait()
    os.remove(zipname)


    # This section will run makedomainenv on lambda-build-server however
    # running it this way seems to cause the virtualenv to get messed up.
    # Running this script manually on the build server does not have the problem.
    print("calling makedomainenv on lambda-build-server")
    #cmd = "\"shopt login_shell\""
    cmd = "\"source /etc/profile && source ~/.bash_profile && /home/ec2-user/makedomainenv {}\"".format(domain)
    ssh(apl_bastion_key, LAMBDA_BUILD_SERVER, "ec2-user", cmd)

def create_session(credentials):
    """Read the AWS from the credentials dictionary and then create a boto3
    connection to AWS with those credentials.

    Args:
        credentials (optional[dict]): If not supplied, will assume the machine has permissions applied.

    Returns:
        (boto3.Session)
    """
    if credentials is not None:
        session = Session(
            aws_access_key_id=credentials["aws_access_key"],
            aws_secret_access_key=credentials["aws_secret_key"],
            region_name=AWS_REGION)
    else:
        session = Session(region_name=AWS_REGION)

    return session

def setup_parser():
    parser = argparse.ArgumentParser(
        description='Script for updating lambda function code.  To supply arguments from a file, provide the filename prepended with an `@`.',
        fromfile_prefix_chars = '@')
    parser.add_argument(
        '--aws-credentials', '-a',
        metavar = '<file>',
        default = os.environ.get('AWS_CREDENTIALS'),
        type = argparse.FileType('r'),
        help = 'File with credentials for connecting to AWS (default: AWS_CREDENTIALS)')
    parser.add_argument(
        'domain',
        help = 'Domain that lambda functions live in, such as integration.boss.')
    # parser.add_argument(
    # parser.add_argument(
    #     '--bucket', '-b',
    #     default = S3_BUCKET,
    #     help = 'Name of S3 bucket containing lambda function.')
    #     '--key',
    #     default = None,
    #     help = 'S3 key that identifies zip containing lambda function.')

    return parser

if __name__ == '__main__':
    parser = setup_parser()
    args = parser.parse_args()

    if args.aws_credentials is None:
        credentials = None
    else:
        credentials = json.load(args.aws_credentials)

    session = create_session(credentials)

    load_lambdas_on_s3(args.domain)
    update_lambda_code(session, args.domain)

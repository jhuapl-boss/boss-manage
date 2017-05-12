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
from lib.ssh import SSHConnection
from lib.names import AWSNames
from lib import aws
from lib import utils
from lib import constants as const
from lib import zip

import argparse
import configparser
import os
import sys
import tempfile

# This was an attempt to import CUBOIDSIZE from the spdb repo.  Can't import
# without a compiling spdb's C library.
#
#SPDB_FOLDER = '../salt_stack/salt/spdb/files'
#SPDB_REPO = os.path.normpath(os.path.join(cur_dir, SPDB_FOLDER + '/spdb.git'))
#SPDB_LINK = os.path.normpath(os.path.join(cur_dir, SPDB_FOLDER + '/spdb'))
# try:
#     os.symlink(SPDB_REPO, SPDB_LINK, True)
#     spdb_dir = os.path.normpath(os.path.join(cur_dir, SPDB_FOLDER))
#     sys.path.append(spdb_dir)
#     from spdb.c_lib.c_version.ndtype import CUBOIDSIZE
# finally:
#     os.remove(SPDB_LINK)

# Location of settings files for ndingest.
NDINGEST_SETTINGS_FOLDER = const.repo_path('salt_stack', 'salt', 'ndingest', 'files', 'ndingest.git', 'settings')

# Template used for ndingest settings.ini generation.
NDINGEST_SETTINGS_TEMPLATE = NDINGEST_SETTINGS_FOLDER + '/settings.ini.apl'

def get_lambda_zip_name(lambda_name, domain):
    """Get name of zip file containing lambda.

    This must match the name created in the makedomainenv script that runs on
    the lambda build server.

    Args:
        lambda_name (string): Name of the lambda to build
        domain (string): The VPC's domain name such as integration.boss.

    Returns:
        (string)
    """
    return '{}.{}.zip'.format(lambda_name, domain)

def update_lambda_code(session, lambda_name, domain, bucket):
    names = AWSNames(domain)
    client = session.client('lambda')
    resp = client.update_function_code(
        FunctionName=names.__getattr__(lambda_name),
        S3Bucket=bucket,
        S3Key=get_lambda_zip_name(lambda_name, domain),
        Publish=True)
    print(resp)

# DP TODO: Move to a lib/ library
def load_lambdas_on_s3(session, lambda_name, domain, bucket):
    """Zip up spdb, bossutils, lambda and lambda_utils.  Upload to S3.

    Uses the lambda build server (an Amazon Linux AMI) to compile C code and
    prepare the virtualenv that's ultimately contained in the zip file placed
    in S3.

    Args:
        session (Session): boto3.Session
        lambda_name (string): Name of the lambda to build
        domain (string): The VPC's domain name such as integration.boss.
    """
    tempname = tempfile.NamedTemporaryFile(delete=True)
    zipname = tempname.name + '.zip'
    tempname.close()
    print('Using temp zip file: ' + zipname)

    is_multi = lambda_name == "multi_lambda"

    cwd = os.getcwd()
    os.chdir(const.repo_path("salt_stack", "salt", "boss-tools", "files", "boss-tools.git", "lambda"))
    if not is_multi:
        zip.write_to_zip(lambda_name + '.py', zipname, False) # Create a new zip file

    requirements = lambda_name + '.requirements'
    if os.path.exists(requirements):
        zip.write_to_zip(requirements, zipname, arcname='requirements.txt')

    packages = lambda_name + '.packages'
    if os.path.exists(packages):
        zip.write_to_zip(packages, zipname, arcname='packages.txt')

    boss = lambda_name + '.boss'
    if os.path.exists(boss):
        with open(boss, 'r') as fh:
            boss = [l.strip() for l in fh.read().split('\n')]
    else:
        boss = []

    site_pkgs = "lib/python3.5/dist-packages/"
    if is_multi:
        os.chdir(const.repo_path("salt_stack", "salt", "boss-tools", "files", "boss-tools.git"))
        zip.write_to_zip('lambda', zipname, arcname=site_pkgs + "lambda")
        zip.write_to_zip('lambdautils', zipname, arcname=site_pkgs + "lambdautils")

        os.chdir(const.repo_path("salt_stack", "salt", "boss-tools", "files", "boss-tools.git", "lambda"))
        zip.write_to_zip('lambda_loader.py', zipname)

    if 'multidimensional' in boss:
        os.chdir(const.repo_path("salt_stack", "salt", "boss-tools", "files", "boss-tools.git", "activities"))
        zip.write_to_zip('multidimensional.py', zipname, arcname=site_pkgs + "multidimensional/__init__.py")

    if 'bossutils' in boss:
        os.chdir(const.repo_path("salt_stack", "salt", "boss-tools", "files", "boss-tools.git"))
        zip.write_to_zip('bossutils', zipname, arcname=site_pkgs + 'bossutils')

    if 'spdb' in boss:
        os.chdir(const.repo_path("salt_stack", "salt", "spdb", "files"))
        zip.write_to_zip('spdb.git', zipname, arcname=site_pkgs + 'spdb')

    if 'ndingest' in boss:
        with open(NDINGEST_SETTINGS_TEMPLATE, 'r') as tmpl:
            # Generate settings.ini file for ndingest.
            create_ndingest_settings(domain, tmpl)

        os.chdir(const.repo_path("salt_stack", "salt", "ndingest", "files"))
        zip.write_to_zip('ndingest.git', zipname, arcname=site_pkgs + 'ndingest')

    os.chdir(cwd)

    print("Copying local modules to lambda-build-server")

    #copy the zip file to lambda_build_server
    lambda_build_server = aws.get_lambda_server(session)
    lambda_build_server_key = aws.get_lambda_server_key(session)
    lambda_build_server_key = utils.keypair_to_file(lambda_build_server_key)
    ssh = SSHConnection(lambda_build_server_key, (lambda_build_server, 22, 'ec2-user'))
    target_file = "sitezips/{}.{}.zip".format(lambda_name, domain)
    ret = ssh.scp(zipname, target_file, upload=True)
    print("scp return code: " + str(ret))

    os.remove(zipname)

    # This section will run makedomainenv on lambda-build-server
    print("calling makedomainenv on lambda-build-server")
    cmd = 'source /etc/profile && source ~/.bash_profile && /home/ec2-user/makedomainenv {}.{} {}'.format(lambda_name, domain, bucket)
    ssh.cmd(cmd)

def create_ndingest_settings(domain, fp):
    """Create the settings.ini file for ndingest.

    The file is placed in ndingest's settings folder.j

    Args:
        domain (string): The VPC's domain name such as integration.boss.
        fp (file-like object): File like object to read settings.ini template from.
    """
    names = AWSNames(domain)
    parser = configparser.ConfigParser()
    parser.read_file(fp)

    parser['boss']['domain'] = domain

    parser['aws']['tile_bucket'] = names.tile_bucket
    parser['aws']['cuboid_bucket'] = names.cuboid_bucket
    parser['aws']['tile_index_table'] = names.tile_index
    parser['aws']['cuboid_index_table'] = names.s3_index

    # parser['spdb']['SUPER_CUBOID_SIZE'] = CUBOIDSIZE[0]
    # ToDo: find way to always get cuboid size from spdb.
    parser['spdb']['SUPER_CUBOID_SIZE'] = '512, 512, 16'

    with open(NDINGEST_SETTINGS_FOLDER + '/settings.ini', 'w') as out:
        parser.write(out)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Script for updating lambda function code. ' + 
                                     'To supply arguments from a file, provide the filename prepended with an `@`.',
                                     fromfile_prefix_chars = '@')
    parser.add_argument('--aws-credentials', '-a',
                        metavar = '<file>',
                        default = os.environ.get('AWS_CREDENTIALS'),
                        type = argparse.FileType('r'),
                        help = 'File with credentials for connecting to AWS (default: AWS_CREDENTIALS)')
    parser.add_argument('name',
                        help = 'Name of the lambda function to build')
    parser.add_argument('domain',
                        help = 'Domain that lambda functions live in, such as integration.boss.')

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    session = aws.create_session(args.aws_credentials)
    bucket = aws.get_lambda_s3_bucket(session)

    load_lambdas_on_s3(session, args.name, args.domain, bucket)
    update_lambda_code(session, args.name, args.domain, bucket)

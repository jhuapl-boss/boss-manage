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
from lib.ssh import SSHConnection, SSHTarget
from lib.names import AWSNames
from lib import configuration
from lib import aws
from lib import utils
from lib import constants as const
from lib import zip

import argparse
import botocore
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

def update_lambda_code(bosslet_config):
    """Update all lambdas that use the multilambda zip file.

    Args:
        bosslet_config: Bosslet configuration object
    """
    names = AWSNames(bosslet_config)
    uses_multilambda = [
        names.lambda_.multi_lambda, 
        names.lambda_.downsample_volume,
        names.lambda_.delete_tile_objs,
        names.lambda_.delete_tile_index_entry,
        names.lambda_.index_s3_writer, 
        names.lambda_.index_fanout_id_writer,
        names.lambda_.index_write_id,
        names.lambda_.index_write_failed,
        names.lambda_.index_find_cuboids,
        names.lambda_.index_split_cuboids,
        names.lambda_.index_fanout_enqueue_cuboid_keys,
        names.lambda_.index_batch_enqueue_cuboids,
        names.lambda_.index_fanout_dequeue_cuboid_keys,
        names.lambda_.index_dequeue_cuboid_keys,
        names.lambda_.index_get_num_cuboid_keys_msgs,
        names.lambda_.index_check_for_throttling,
        names.lambda_.index_invoke_index_supervisor,
        names.lambda_.start_sfn,
        names.lambda_.downsample_volume,
    ]
    client = bosslet_config.session.client('lambda')
    for lambda_name in uses_multilambda:
        try:
            resp = client.update_function_code(
                FunctionName=lambda_name,
                S3Bucket=bosslet_config.LAMBDA_BUCKET,
                S3Key=names.zip.multi_lambda,
                Publish=True)
            print(resp)
        except botocore.exceptions.ClientError as ex:
            print('Error updating {}: {}'.format(lambda_name, ex))

# DP TODO: Move to a lib/ library
def load_lambdas_on_s3(bosslet_config):
    """Zip up spdb, bossutils, lambda and lambda_utils.  Upload to S3.

    Uses the lambda build server (an Amazon Linux AMI) to compile C code and
    prepare the virtualenv that's ultimately contained in the zip file placed
    in S3.

    Args:
        session (Session): boto3.Session
        domain (str): The VPC's domain name such as integration.boss.
        bucket (str): Name of bucket that contains the lambda zip file.
    """
    domain = bosslet_config.INTERNAL_DOMAIN
    tempname = tempfile.NamedTemporaryFile(delete=True)
    zipname = tempname.name + '.zip'
    tempname.close()
    print('Using temp zip file: ' + zipname)

    cwd = os.getcwd()
    os.chdir(const.repo_path("salt_stack", "salt", "spdb", "files"))
    zip.write_to_zip('spdb.git', zipname, False)
    os.chdir(cwd)

    os.chdir(const.repo_path("salt_stack", "salt", "boss-tools", "files", "boss-tools.git"))
    zip.write_to_zip('bossutils', zipname)
    zip.write_to_zip('cloudwatchwrapper', zipname)
    zip.write_to_zip('lambda', zipname)
    zip.write_to_zip('lambdautils', zipname)
    os.chdir(cwd)

    with open(NDINGEST_SETTINGS_TEMPLATE, 'r') as tmpl:
        # Generate settings.ini file for ndingest.
        create_ndingest_settings(bosslet_config, tmpl)

    os.chdir(const.repo_path("salt_stack", "salt", "ndingest", "files"))
    zip.write_to_zip('ndingest.git', zipname)
    os.chdir(cwd)

    os.chdir(const.repo_path("lib"))
    zip.write_to_zip('heaviside.git', zipname)

    # Let lambdas look up names by creating a bossnames module.
    zip.write_to_zip('names.py', zipname, arcname='bossnames/names.py')
    zip.write_to_zip('hosts.py', zipname, arcname='bossnames/hosts.py')
    zip.write_to_zip('__init__.py', zipname, arcname='bossnames/__init__.py')
    os.chdir(cwd)

    print("Copying local modules to lambda-build-server")

    #copy the zip file to lambda_build_server
    lambda_bucket = bosslet_config.LAMBDA_BUCKET
    lambda_build_server = bosslet_config.LAMBDA_SERVER
    lambda_build_server_key = bosslet_config.LAMBDA_SERVER_KEY
    lambda_build_server_key = utils.keypair_to_file(lambda_build_server_key)
    ssh_target = SSHTarget(lambda_build_server_key, lambda_build_server, 22, 'ec2-user')
    bastions = [bosslet_config.outbound_bastion] if bosslet_config.outbound_bastion else []
    ssh = SSHConnection(ssh_target, bastions)
    target_file = "sitezips/{}.zip".format(domain)
    ret = ssh.scp(zipname, target_file, upload=True)
    print("scp return code: " + str(ret))

    os.remove(zipname)

    # This section will run makedomainenv on lambda-build-server
    print("calling makedomainenv on lambda-build-server")
    cmd = 'source /etc/profile && source ~/.bash_profile && /home/ec2-user/makedomainenv {} {}'.format(domain, lambda_bucket)
    ret = ssh.cmd(cmd)
    print("ssh return code: " + str(ret))

def create_ndingest_settings(bosslet_config, fp):
    """Create the settings.ini file for ndingest.

    The file is placed in ndingest's settings folder.

    Args:
        domain (str): The VPC's domain name such as integration.boss.
        fp (file-like object): File like object to read settings.ini template from.
    """
    names = AWSNames(bosslet_config)
    parser = configparser.ConfigParser()
    parser.read_file(fp)

    parser['boss']['domain'] = bosslet_config.INTERNAL_DOMAIN

    parser['aws']['tile_bucket'] = names.s3.tile_bucket
    parser['aws']['cuboid_bucket'] = names.s3.cuboid_bucket
    parser['aws']['tile_index_table'] = names.ddb.tile_index
    parser['aws']['cuboid_index_table'] = names.ddb.s3_index
    parser['aws']['max_task_id_suffix'] = str(const.MAX_TASK_ID_SUFFIX)

    # parser['spdb']['SUPER_CUBOID_SIZE'] = CUBOIDSIZE[0]
    # ToDo: find way to always get cuboid size from spdb.
    parser['spdb']['SUPER_CUBOID_SIZE'] = '512, 512, 16'

    with open(NDINGEST_SETTINGS_FOLDER + '/settings.ini', 'w') as out:
        parser.write(out)

if __name__ == '__main__':
    parser = configuration.BossParser(description='Script for updating lambda function code. ' + 
                                      'To supply arguments from a file, provide the filename prepended with an `@`.',
                                      fromfile_prefix_chars = '@')
    parser.add_bosslet()

    args = parser.parse_args()

    load_lambdas_on_s3(args.bosslet_config)
    update_lambda_code(args.bosslet_config)

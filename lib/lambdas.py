# Copyright 2019 The Johns Hopkins University Applied Physics Laboratory
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

from lib.ssh import SSHConnection, SSHTarget
from lib import utils
from lib import constants as const
from lib import zip

import botocore
import configparser
import os
import tempfile

# Location of settings files for ndingest.
NDINGEST_SETTINGS_FOLDER = const.repo_path('salt_stack', 'salt', 'ndingest', 'files', 'ndingest.git', 'settings')

# Template used for ndingest settings.ini generation.
NDINGEST_SETTINGS_TEMPLATE = NDINGEST_SETTINGS_FOLDER + '/settings.ini.apl'

def update_lambda_code(bosslet_config):
    """Update all lambdas that use the multilambda zip file.

    Args:
        bosslet_config: Bosslet configuration object
    """
    names = bosslet_config.names
    uses_multilambda = [
        names.multi_lambda.lambda_, 
        names.downsample_volume.lambda_,
        names.delete_tile_objs.lambda_,
        names.delete_tile_index_entry.lambda_,
        names.index_s3_writer.lambda_, 
        names.index_fanout_id_writer.lambda_,
        names.index_write_id.lambda_,
        names.index_write_failed.lambda_,
        names.index_find_cuboids.lambda_,
        names.index_split_cuboids.lambda_,
        names.index_fanout_enqueue_cuboid_keys.lambda_,
        names.index_batch_enqueue_cuboids.lambda_,
        names.index_fanout_dequeue_cuboid_keys.lambda_,
        names.index_dequeue_cuboid_keys.lambda_,
        names.index_get_num_cuboid_keys_msgs.lambda_,
        names.index_check_for_throttling.lambda_,
        names.index_invoke_index_supervisor.lambda_,
        names.start_sfn.lambda_,
        names.downsample_volume.lambda_,
        names.copy_cuboid_lambda.lambda_,
        names.tile_uploaded.lambda_,
        names.tile_ingest.lambda_,
    ]
    client = bosslet_config.session.client('lambda')
    for lambda_name in uses_multilambda:
        try:
            resp = client.update_function_code(
                FunctionName=lambda_name,
                S3Bucket=bosslet_config.LAMBDA_BUCKET,
                S3Key=names.multi_lambda.zip,
                Publish=True)
            print(resp)
        except botocore.exceptions.ClientError as ex:
            print('Error updating {}: {}'.format(lambda_name, ex))

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
    zip.write_to_zip('bucket_object_tags.py', zipname, arcname='bossnames/bucket_object_tags.py')
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
    names = bosslet_config.names
    parser = configparser.ConfigParser()
    parser.read_file(fp)

    parser['boss']['domain'] = bosslet_config.INTERNAL_DOMAIN

    parser['aws']['tile_bucket'] = names.tile_bucket.s3
    parser['aws']['cuboid_bucket'] = names.cuboid_bucket.s3
    parser['aws']['tile_index_table'] = names.tile_index.ddb
    parser['aws']['cuboid_index_table'] = names.s3_index.ddb
    parser['aws']['max_task_id_suffix'] = str(const.MAX_TASK_ID_SUFFIX)

    # parser['spdb']['SUPER_CUBOID_SIZE'] = CUBOIDSIZE[0]
    # ToDo: find way to always get cuboid size from spdb.
    parser['spdb']['SUPER_CUBOID_SIZE'] = '512, 512, 16'

    with open(NDINGEST_SETTINGS_FOLDER + '/settings.ini', 'w') as out:
        parser.write(out)

def freshen_lambda(bosslet_config, lambda_name):
    """
    Tell a lambda to reload its code from S3.  

    Useful when developing and small changes need to be made to a lambda function, 
    but a full rebuild of the entire zip file isn't required.
    """
    zip_name = bosslet_config.names.multi_lambda.zip
    full_name = bosslet_config.names[lambda_name].lambda_
    client = bosslet_config.session.client('lambda')
    resp = client.update_function_code(
        FunctionName=full_name,
        S3Bucket=bosslet_config.LAMBDA_BUCKET,
        S3Key=zip_name,
        Publish=True)
    print(resp)

def download_lambda_zip(bosslet_config, path):
    """
    Download the existing multilambda.domain.zip from the S3 bucket.  Useful when
    developing and small changes need to be made to a lambda function, but a full
    rebuild of the entire zip file isn't required.
    """
    s3 = bosslet_config.session.client('s3')
    zip_name = bosslet_config.names.multi_lambda.zip
    full_path = '{}/{}'.format(path, zip_name)
    resp = s3.get_object(Bucket=bosslet_config.LAMBDA_BUCKET, Key=zip_name)

    bytes = resp['Body'].read()

    with open(full_path , 'wb') as out:
        out.write(bytes)

    print('Saved zip to {}'.format(full_path))

def upload_lambda_zip(bosslet_config, path):
    """
    Upload a  multilambda.domain.zip to the S3 bucket.  Useful when
    developing and small changes need to be made to a lambda function, but a full
    rebuild of the entire zip file isn't required.
    """
    s3 = bosslet_config.session.client('s3')
    with open(path, 'rb') as in_file:
        resp = s3.put_object(Bucket=bosslet_config.LAMBDA_BUCKET,
                             Key=bosslet_config.names.multi_lambda.zip,
                             Body=in_file)
    print(resp)


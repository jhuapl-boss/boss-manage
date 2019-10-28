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
import yaml
import glob
import os
import tempfile
import subprocess
import shlex
import shutil
import pwd
import pathlib

# Location of settings files for ndingest.
NDINGEST_SETTINGS_FOLDER = const.repo_path('salt_stack', 'salt', 'ndingest', 'files', 'ndingest.git', 'settings')

# Template used for ndingest settings.ini generation.
NDINGEST_SETTINGS_TEMPLATE = NDINGEST_SETTINGS_FOLDER + '/settings.ini.apl'

def build_lambda(bosslet_config, lambda_name):
    lambda_dir = pathlib.Path(const.repo_path('cloud_formation', 'lambda', lambda_name))
    lambda_config = lambda_dir / 'lambda.yml'
    with lambda_config.open() as fh:
        lambda_config = yaml.load(fh.read())

    domain = bosslet_config.INTERNAL_DOMAIN
    tempname = tempfile.NamedTemporaryFile(delete=True)
    zipname = pathlib.Path(tempname.name + '.zip')
    tempname.close()
    print('Using temp zip file: {}'.format(zipname))

    cwd = os.getcwd()

    # Copy the lambda files into the zip
    for filename in lambda_dir.glob('*'):
        zip.write_to_zip(str(filename), zipname, arcname=filename.name)

    # Copy the other files that should be included
    if 'include' in lambda_config:
        for src in lambda_config['include']:
            dst = lambda_config['include'][src]
            src_path, src_file = src.rsplit('/', 1)

            os.chdir(src_path)

            # Generate dynamic configuration files, as needed
            if src_file == 'ndingest.git':
                with open(NDINGEST_SETTINGS_TEMPLATE, 'r') as tmpl:
                    # Generate settings.ini file for ndingest.
                    create_ndingest_settings(bosslet_config, tmpl)

            zip.write_to_zip(src_file, zipname, arcname=dst)
            os.chdir(cwd)

    CONTAINER_CMD = 'podman run --rm -it --volume {HOST_DIR}:/var/task/ lambci/lambda:build-{RUNTIME} {CMD}'

    BUILD_CMD = 'python3 {PREFIX}/build_lambda.py {DOMAIN} {BUCKET}'
    BUILD_ARGS = {
        'DOMAIN': domain,
        'BUCKET': bosslet_config.LAMBDA_BUCKET,
    }

    lambda_build_server = None #bosslet_config.LAMBDA_SERVER
    container_command = True
    if lambda_build_server is None:
        staging_target = pathlib.Path(const.repo_path('salt_stack', 'salt', 'lambda-dev', 'files', 'staging'))
        if not staging_target.exists():
            staging_target.mkdir()

        utils.run('ls -la {}'.format(zipname), shell=True)

        print("Copying build zip to {}".format(staging_target))
        staging_zip = staging_target / (domain + '.zip')
        try:
            zipname.rename(staging_zip)
        except OSError:
            # rename only works within the same filesystem
            # Using the shell version, as chmod doesn't always work depending on the filesystem
            utils.run('mv {} {}'.format(zipname, staging_zip), shell=True)

        if container_command is None:
            BUILD_ARGS['PREFIX'] = const.repo_path('salt_stack', 'salt', 'lambda-dev', 'files')
            CMD = BUILD_CMD.format(**BUILD_ARGS)
        else:
            BUILD_ARGS['PREFIX'] = '/var/task'
            CMD = BUILD_CMD.format(**BUILD_ARGS)
            CMD = CONTAINER_CMD.format(HOST_DIR = const.repo_path('salt_stack', 'salt', 'lambda-dev', 'files'),
                                       RUNTIME = lambda_config['runtime'],
                                       CMD = CMD)

        print(CMD)

        try:
            print("calling makedomainenv on localhost")

            try:
                utils.run(CMD)
            except Exception as ex:
                print("makedomainenv return code: {}".format(ex))
                # DP NOTE: currently eating the error, as there is no checking of error if there is a build server
        finally:
            os.remove(staging_zip)

    else:
        BUILD_ARGS['PREFIX'] = '~'
        CMD = BUILD_CMD.format(**BUILD_ARGS)
        print(CMD); return

        lambda_build_server_key = bosslet_config.LAMBDA_SERVER_KEY
        lambda_build_server_key = utils.keypair_to_file(lambda_build_server_key)
        ssh_target = SSHTarget(lambda_build_server_key, lambda_build_server, 22, 'ec2-user')
        bastions = [bosslet_config.outbound_bastion] if bosslet_config.outbound_bastion else []
        ssh = SSHConnection(ssh_target, bastions)

        print("Copying build zip to lambda-build-server")
        ret = ssh.scp(zipname, target_file, upload=True)
        print("scp return code: " + str(ret))

        os.remove(zipname)

        print("calling makedomainenv on lambda-build-server")
        ret = ssh.cmd(CMD)
        print("ssh return code: " + str(ret))

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
        names.index_load_ids_from_s3.lambda_,
        names.start_sfn.lambda_,
        names.copy_cuboid_lambda.lambda_,
        names.cuboid_import_lambda.lambda_,
        names.volumetric_ingest_queue_upload_lambda.lambda_,
        names.tile_uploaded.lambda_,
        names.tile_ingest.lambda_,
        names.delete_tile_index_entry.lambda_,
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


    #copy the zip file to lambda_build_server and run makedomainenv
    lambda_bucket = bosslet_config.LAMBDA_BUCKET

    build_cmd = 'source /etc/profile && source ~/.bash_profile && ~/makedomainenv {} {}'.format(domain, lambda_bucket)
    target_file = "sitezips/{}.zip".format(domain)

    lambda_build_server = bosslet_config.LAMBDA_SERVER
    if lambda_build_server is None:
        print("Copying local modules to localhost")
        full_target_file = '/home/ec2-user/' + target_file
        shutil.copy(zipname, full_target_file)
        os.remove(zipname)

        cur_user = pwd.getpwuid(os.getuid()).pw_name
        if cur_user != 'ec2-user':
            # Correctly set the $HOME directory so the makedomainenv script works correctly
            build_cmd = build_cmd.replace('~', '/home/ec2-user')
            build_cmd = 'HOME=/home/ec2-user su -m ec2-user -c "{}"'.format(build_cmd)

        try:
            print("calling makedomainenv on localhost")

            output = subprocess.check_output(build_cmd,
                                             shell=True,
                                             executable='/bin/bash',
                                             stderr=subprocess.STDOUT)
            print(output.decode('utf-8'))
        except subprocess.CalledProcessError as ex:
            print("makedomainenv return code: {}".format(ex.returncode))
            print(ex.output.decode('utf-8'))
            # DP NOTE: currently eating the error, as there is no checking of error if there is a build server
        finally:
            os.remove(full_target_file)
    else:
        lambda_build_server_key = bosslet_config.LAMBDA_SERVER_KEY
        lambda_build_server_key = utils.keypair_to_file(lambda_build_server_key)
        ssh_target = SSHTarget(lambda_build_server_key, lambda_build_server, 22, 'ec2-user')
        bastions = [bosslet_config.outbound_bastion] if bosslet_config.outbound_bastion else []
        ssh = SSHConnection(ssh_target, bastions)

        print("Copying local modules to lambda-build-server")
        ret = ssh.scp(zipname, target_file, upload=True)
        print("scp return code: " + str(ret))

        os.remove(zipname)

        # This section will run makedomainenv on lambda-build-server
        print("calling makedomainenv on lambda-build-server")
        ret = ssh.cmd(build_cmd)
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

    parser['aws']['region'] = bosslet_config.REGION
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


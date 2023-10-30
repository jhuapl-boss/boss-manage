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

from lib.exceptions import BossManageError
from lib.ssh import SSHConnection, SSHTarget
from lib import utils
from lib import constants as const
from lib import zip
from lib import console
from lib.hash import FilesHash

import botocore
import boto3
import configparser
import yaml
import os
import tempfile
import pathlib
from pprint import pprint
import hashlib

# Location of settings files for ndingest.
NDINGEST_SETTINGS_FOLDER = const.repo_path('salt_stack', 'salt', 'ndingest', 'files', 'ndingest.git', 'ndingest', 'settings')

# Template used for ndingest settings.ini generation.
NDINGEST_SETTINGS_TEMPLATE = NDINGEST_SETTINGS_FOLDER + '/settings.ini.apl'

def load_lambda_config(lambda_dir):
    """Load the lambda.yml config file

    Args:
        lambda_dir (str): Name of the directory under cloud_formation/lambda/ that
                          contains the lambda.yml file to load

    Returns:
        dict: Dictionary of configuration file data
    """
    lambda_config = const.repo_path('cloud_formation', 'lambda', lambda_dir, 'lambda.yml')
    with open(lambda_config, 'r') as fh:
        return yaml.full_load(fh.read())

def lambda_dirs(bosslet_config):
    """Create a mapping of lambda name to lambda directory

    Note: The lambda directory is the directory in cloud_formation/lambdas/ that
          contains the lambda.yml for building the lambda's code zip

    Args:
        bosslet_config: Bosslet configuration object

    Returns:
        dict: Mapping of lambda name to lambda directory
    """
    n = bosslet_config.names
    # DP NOTE: Values must be the name of a directory under cloud_formation/lambdas/
    return {
        n.multi_lambda.lambda_: 'multi_lambda',
        n.downsample_volume.lambda_: 'multi_lambda',
        n.delete_tile_objs.lambda_: 'multi_lambda',
        n.delete_tile_index_entry.lambda_: 'multi_lambda',
        n.index_s3_writer.lambda_: 'multi_lambda', 
        n.index_write_id.lambda_: 'multi_lambda',
        n.index_write_failed.lambda_: 'multi_lambda',
        n.index_find_cuboids.lambda_: 'multi_lambda',
        n.index_batch_enqueue_cuboids.lambda_: 'multi_lambda',
        n.index_enqueue_ids.lambda_: 'multi_lambda',
        n.index_load_ids_from_s3.lambda_: 'multi_lambda',
        n.start_sfn.lambda_: 'multi_lambda',
        n.copy_cuboid_lambda.lambda_: 'multi_lambda',
        n.cuboid_import_lambda.lambda_: 'multi_lambda',
        n.volumetric_ingest_queue_upload_lambda.lambda_: 'multi_lambda',
        n.tile_uploaded.lambda_: 'multi_lambda',
        n.tile_ingest.lambda_: 'multi_lambda',
        n.delete_tile_index_entry.lambda_: 'multi_lambda',
        n.start_sfn.lambda_: 'multi_lambda',
        n.downsample_volume.lambda_: 'multi_lambda',
        n.dynamo_lambda.lambda_: 'dynamodb-lambda-autoscale'
    }

def code_zip(bosslet_config, lambda_config):
    """Get the name of the lambda code zip file

    DP NOTE: Must match what salt_stack/salt/lambda-dev/files/build_lambda.py does
             when uploading the results to S3

    Args:
        bosslet_config: Bosslet configuration object
        lambda_config (dict): Lambda configuration data

    Returns:
        str: Name of the lambda code zip file
    """
    return lambda_config['name'] + '.' + bosslet_config.INTERNAL_DOMAIN + '.zip'

def get_layer_arns(bosslet_config, layer_dirs):
    """Lookup the latest version ARNs for the given layers

    DP NOTE: Must match what salt_stack/salt/lambda-dev/files/build_lambda.py does
             when creating a Lambda Layer

    Args:
        bosslet_config: Bosslet configuration object
        layer_dirs (list[str]): List of layer_dir names

    Returns:
        list[str]: List of Lambda Layer Version ARNs
    """
    client = bosslet_config.session.client('lambda')

    layers = []
    for layer_dir in layer_dirs:
        layer_config = load_lambda_config(layer_dir)
        layer_name = (layer_config['name'] + '.' + bosslet_config.INTERNAL_DOMAIN).replace('.', '-')

        resp = client.list_layer_versions(LayerName=layer_name)
        arn = resp['LayerVersions'][0]['LayerVersionArn']
        layers.append(arn)

    return layers

def s3_config(bosslet_config, lambda_name, lambda_handler):
    """Look up the configuration information needed by CloudFormationTemplate

    Used by lib.cloudformation.CloudFormationTemplate.add_lambda if only a lambda
    handler is defined

    Args:
        bosslet_config: Bosslet configuration object
        lambda_name (str): Full name of the lambda
        lambda_handler (str): Name of the lambda handler

    Returns:
        tuple[tuple[str, str, str], str, optional[list[str]]]:
            Tuple of arguments for CloudFormationTemplate.add_lambda
            kwargs s3, runtime, and layers

    """
    lambda_dir = lambda_dirs(bosslet_config)[lambda_name]

    config = load_lambda_config(lambda_dir)

    layers = None
    if config.get('layers'):
        layers = get_layer_arns(bosslet_config, config['layers'])

    return ((bosslet_config.LAMBDA_BUCKET,
             code_zip(bosslet_config, config),
             lambda_handler),
            config['runtime'],
            layers)

def update_lambda_code(bosslet_config):
    """Update all lambdas that use the multilambda zip file.

    Args:
        bosslet_config: Bosslet configuration object
    """
    uses_multilambda = [k for k, v in lambda_dirs(bosslet_config).items()
                          if v == 'multi_lambda']
    config = load_lambda_config('multi_lambda')
    client = bosslet_config.session.client('lambda')
    for lambda_name in uses_multilambda:
        try:
            resp = client.update_function_code(
                FunctionName=lambda_name,
                S3Bucket=bosslet_config.LAMBDA_BUCKET,
                S3Key=code_zip(bosslet_config, config),
                Publish=True)
            print(resp)
        except botocore.exceptions.ClientError as ex:
            print('Error updating {}: {}'.format(lambda_name, ex))

BUILT_ZIPS = []
def load_lambdas_on_s3(bosslet_config, lambda_name = None, lambda_dir = None):
    """Package up the lambda files and send them through the lambda build process
    where the lambda code zip is produced and uploaded to S3

    NOTE: This function is also used to build lambda layer code zips, the only requirement
          for a layer is that the files in the resulting zip should be in the correct
          subdirectory (`python/` for Python libraries) so that when a lambda uses the
          layer the libraries included in the layer can be correctly loaded

    NOTE: If lambda_name and lambda_dir are both None then lambda_dir is set to
          'multi_lambda' for backwards compatibility

    Args:
        bosslet_config (BossConfiguration): Configuration object of the stack the
                                            lambda will be deployed into
        lambda_name (str): Name of the lambda, which will be mapped to the name of the
                           lambda directory that contains the lambda's code
        lambda_dir (str): Name of the directory in `cloud_formation/lambda/` that
                          contains the `lambda.yml` configuration file for the lambda

    Raises:
        BossManageError: If there was a problem with building the lambda code zip or
                         uploading it to the given S3 bucket
    """
    # For backwards compatibility build the multi_lambda code zip
    if lambda_name is None and lambda_dir is None:
        lambda_dir = 'multi_lambda'

    # Map from lambda_name to lambda_dir if needed
    if lambda_dir is None:
        try:
            lambda_dir = lambda_dirs(bosslet_config)[lambda_name]
        except KeyError:
            console.error("Cannot build a lambda that doesn't use a code zip file")
            return None

    # To prevent rebuilding a lambda code zip multiple times during an individual execution memorize what has been built
    if lambda_dir in BUILT_ZIPS:
        console.debug('Lambda code {} already built recently, skipping...'.format(lambda_dir))
        return
    BUILT_ZIPS.append(lambda_dir)

    lambda_dir = pathlib.Path(const.repo_path('cloud_formation', 'lambda', lambda_dir))
    lambda_config = lambda_dir / 'lambda.yml'
    with lambda_config.open() as fh:
        lambda_config = yaml.full_load(fh.read())

    if lambda_config.get('layers'):
        for layer in lambda_config['layers']:
            # Layer names should end with `layer`
            if not layer.endswith('layer'):
                console.warning("Layer '{}' doesn't conform to naming conventions".format(layer))

            load_lambdas_on_s3(bosslet_config, lambda_dir=layer)

    console.debug("Building {} lambda code zip".format(lambda_dir))

    domain = bosslet_config.INTERNAL_DOMAIN
    tempname = tempfile.NamedTemporaryFile(delete=True)
    zipname = pathlib.Path(tempname.name + '.zip')
    tempname.close()
    console.debug('Using temp zip file: {}'.format(zipname))

    cwd = os.getcwd()

    hasher = FilesHash(get_sha256())

    # Copy the lambda files into the zip
    for filename in lambda_dir.glob('*'):
        zip.write_to_zip(str(filename), zipname, arcname=filename.name, callback=hasher.add_file)

    # Copy the other files that should be included
    if lambda_config.get('include'):
        for src in lambda_config['include']:
            dst = lambda_config['include'][src]
            src_path, src_file = src.rsplit('/', 1)

            os.chdir(const.repo_path(src_path))

            # Generate dynamic configuration files, as needed
            if src_file == 'ndingest.git':
                with open(NDINGEST_SETTINGS_TEMPLATE, 'r') as tmpl:
                    # Generate settings.ini file for ndingest.
                    create_ndingest_settings(bosslet_config, tmpl)

            zip.write_to_zip(src_file, zipname, arcname=dst, callback=hasher.add_file)
            os.chdir(cwd)

    cmd_parts = [
        'docker run --rm -it',
        '-e AWS_ACCESS_KEY_ID={AWS_ACCESS_KEY_ID}',
        '-e AWS_SECRET_ACCESS_KEY={AWS_SECRET_ACCESS_KEY}',
        '-e PIP_CERT=/etc/pki/tls/certs/ca-bundle.crt',
        '-e REQUESTS_CA_BUNDLE=/etc/pki/tls/certs/ca-bundle.crt',
        '-e SSL_CERT_FILE=/etc/pki/tls/certs/ca-bundle.crt',
        '-e PIP_DEFAULT_TIMEOUT=100',
        '--volume {HOST_DIR}:/var/task/',
        '--platform linux/amd64',
        'lambci/lambda:build-{RUNTIME} {CMD}',
    ]
    CONTAINER_CMD = ' '.join(cmd_parts)

    staging_target = pathlib.Path(const.repo_path('salt_stack', 'salt', 'lambda-dev', 'files', 'staging'))
    if not staging_target.exists():
        staging_target.mkdir()

    console.debug("Copying build zip to {}".format(staging_target))
    staging_zip = staging_target / (domain + '.zip')
    try:
        zipname.rename(staging_zip)
    except OSError:
        # rename only works within the same filesystem
        # Using the shell version, as using copy +  chmod doesn't always work depending on the filesystem
        utils.run('mv {} {}'.format(zipname, staging_zip), shell=True)

    zip_hash = hasher.hexdigest
    if not should_build_lambda(
        zip_hash,
        f'{lambda_config["name"]}.{domain}.zip',
        bosslet_config.LAMBDA_BUCKET
    ):
        os.remove(staging_zip)
        return

    hash_file = staging_target / 'lambda_hash.txt';
    hash_file.write_text(zip_hash);

    # Note that we only provide the name of the hash file w/o the path.  The
    # build script expects it in the staging folder.
    BUILD_CMD = f'/var/task/build.sh {domain} {bosslet_config.LAMBDA_BUCKET} {hash_file.name}'

    # Provide the AWS Region and Credentials (for S3 upload) via environmental variables
    env_extras = { 'AWS_REGION': bosslet_config.REGION,
                   'AWS_DEFAULT_REGION': bosslet_config.REGION }

    # Cannot set the profile as the container will not have the credentials file
    # So extract the underlying keys and provide those instead
    creds = bosslet_config.session.get_credentials()
    env_extras['AWS_ACCESS_KEY_ID'] = creds.access_key
    env_extras['AWS_SECRET_ACCESS_KEY'] = creds.secret_key

    # needed to add the AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY directly on the commandline to get them into the environment.
    # the env_extras wasn't working.
    CMD = CONTAINER_CMD.format(AWS_ACCESS_KEY_ID = creds.access_key,
                               AWS_SECRET_ACCESS_KEY = creds.secret_key,
                               HOST_DIR = const.repo_path('salt_stack', 'salt', 'lambda-dev', 'files'),
                               RUNTIME = lambda_config['runtime'],
                               CMD = BUILD_CMD)

    console.info("calling build lambda in Docker")

    try:
        utils.run(CMD, env_extras=env_extras)
    except Exception as ex:
        raise BossManageError("Problem building {} lambda code zip: {}".format(lambda_dir, ex))
    finally:
        os.remove(staging_zip)

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
    lambda_dir = lambda_dirs(bosslet_config)[lambda_name]
    lambda_config = load_lambda_config(lambda_dir)

    zip_name = code_zip(bosslet_config, lambda_config)

    client = bosslet_config.session.client('lambda')
    resp = client.update_function_code(
        FunctionName=lambda_name,
        S3Bucket=bosslet_config.LAMBDA_BUCKET,
        S3Key=zip_name,
        Publish=True)
    console.info("Updated {} function code".format(lambda_name))

    if lambda_config.get('layers'):
        layer_arns = get_layer_arns(bosslet_config, lambda_config['layers'])
        resp = client.update_function_configuration(FunctionName=full_name,
                                                    Layers=layer_arns)
        console.info("Updated {} layer references".format(lambda_name))

def download_lambda_zip(bosslet_config, lambda_name, path):
    """
    Download the existing multilambda.domain.zip from the S3 bucket.  Useful when
    developing and small changes need to be made to a lambda function, but a full
    rebuild of the entire zip file isn't required.
    """
    lambda_dir = lambda_dirs(bosslet_config)[lambda_name]
    lambda_config = load_lambda_config(lambda_dir)

    s3 = bosslet_config.session.client('s3')

    def download(zip_name):
        full_path = os.path.join(path, zip_name)
        resp = s3.get_object(Bucket=bosslet_config.LAMBDA_BUCKET, Key=zip_name)

        bytes = resp['Body'].read()

        with open(full_path , 'wb') as out:
            out.write(bytes)
        print('Saved zip to {}'.format(full_path))

    download(code_zip(bosslet_config, lambda_config))

    if lambda_config.get('layers'):
        for layer in lambda_config['layers']:
            layer_config = load_lambda_config(layer)
            download(code_zip(bosslet_config, layer_config))

def upload_lambda_zip(bosslet_config, path):
    """
    Upload a  multilambda.domain.zip to the S3 bucket.  Useful when
    developing and small changes need to be made to a lambda function, but a full
    rebuild of the entire zip file isn't required.
    """
    s3 = bosslet_config.session.client('s3')
    with open(path, 'rb') as in_file:
        resp = s3.put_object(Bucket=bosslet_config.LAMBDA_BUCKET,
                             Key=os.path.basename(path),
                             Body=in_file)
    print(resp)

def get_sha256():
    """
    Get an instance of the sha256 hash function.  Because we use this just to
    determine if we need to rebuild a lambda function, `usedforsecurity` is
    set to False.
    """
    try:
        sha256 = hashlib.sha256(usedforsecurity=False)
    except Exception:
        # usedforsecurity keyword argument added in Python 3.9.
        sha256 = hashlib.sha256()
    return sha256

def should_build_lambda(zip_hash: str, lambda_zip_name: str, bucket: str) -> bool:
    """
    Compare the hash with the hash of the zip file in S3, if it exists.

    Args:
        zip_hash: SHA256 hash of the zip file that's sent to the build container.
        lambda_zip_name: Object key of lambda zip in S3 bucket.
        bucket: S3 bucket lambda zip lives in.

    Returns:
        True if lambda should be rebuilt.
    """
    s3 = boto3.session.Session().client('s3')
    try:
        resp = s3.head_object(Bucket=bucket, Key=lambda_zip_name)
        metadata = resp['Metadata']
        if metadata['build-hash'] == zip_hash:
            print("Input hash matches existing S3 object, not rebuilding")
            return False
        return True
    except Exception:
        # If there was an error with the check, just rebuild.
        return True

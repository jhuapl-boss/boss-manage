#!/usr/bin/env python3
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

import os
import sys
import time
import glob
import zipfile
import shlex
import shutil
import subprocess
import pathlib



def upload_to_s3(zip_file, target_name, bucket, metadata={}):
    """Upload the zip file to the given S3 bucket.

    Args:
        zip_file (Path): Name of zip file.  The name (after any path is stripped) is used as the key.
        target_name (string): Name to give the zip_File in S3
        bucket (string): Name of bucket to use.
        metadata (dict): Metadata to attach to the file
    """
    session = boto3.session.Session()
    s3 = session.client('s3')
    try:
        s3.create_bucket(Bucket=bucket)
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass # Only us-east-1 will not throw an exception if the bucket already exists

    print("{} -> {}/{}".format(zip_file, bucket, target_name))
    with zip_file.open('rb') as fh:
        s3.put_object(Bucket=bucket, Key=target_name, Body=fh, Metadata=metadata)

def create_layer(bucket, target_name, description):
    """New a new Lambda Layer version

    Args:
        bucket (string): Name of bucket to use.
        target_name (string): Name to give the zip_File in S3
        description (string): Metadata to attach to the file
    """
    session = boto3.session.Session()
    layer_name = target_name[:-4].replace('.', '-') # remove the `.zip`
    
    client = boto3.session.Session().client('lambda')
    resp = client.publish_layer_version(LayerName = layer_name,
                                        Description = description,
                                        Content = {
                                            'S3Bucket': bucket,
                                            'S3Key': target_name
                                        },
                                        LicenseInfo = 'Apache-2.0')
    print("Created Layer {}".format(resp['LayerVersionArn']))

def unzip(zippath, path):
    """Unzip the given zip file to the given directory

    Args:
        zippath (str): Path to the zip file
        path (str): Directory which to unzip into
    """
    fzip = zipfile.ZipFile(zippath, 'r')
    fzip.extractall(path)

def load_config(staging_dir):
    """Load the lambda configuration file from the given directory

    Returns:
        dict: Dictionary of the parsed configuration file
    """
    with open(os.path.join(staging_dir, 'lambda.yml'), 'r') as fh:
        return yaml.full_load(fh.read())

def script_stdout(cmd):
    """Run the following bash script and return the output

    Args:
        cmd (str): The contents of the bash script to run

    Returns:
        str: The results of the script
    """
    proc = subprocess.Popen(['/bin/bash'],
                            cwd = staging_dir,
                            universal_newlines = True, # stdin / stdout are strings instead of bytes
                            stdout = subprocess.PIPE,
                            stdin = subprocess.PIPE)
    stdout, _ = proc.communicate(input = cmd)
    return stdout

def script(cmd):
    """Run the given bash shell script

    Note: This method will stream the results of the script to stdout
          so that for long running scripts the results can be seen
          before the scripts finishes

    Args:
        cmd (str): The contents of the shell script to run

    Raises:
        Exception: If the return code is non-zero
    """
    print("----------------------------------------------------------------------------------")
    print(cmd)

    env = os.environ.copy()
    env['STAGING_DIR'] = staging_dir

    proc = subprocess.Popen(['/bin/bash'],
                            env=env,
                            cwd=staging_dir,
                            bufsize=1, # line bufferred
                            stderr=subprocess.STDOUT,
                            stdout=subprocess.PIPE,
                            stdin=subprocess.PIPE)

    proc.stdin.write(cmd.encode())
    proc.stdin.close()

    for line in proc.stdout:
        print(line.decode('utf8'), end='', flush=True)

    # Verify that the command has finished cleaning up
    # sometime stdout/stderr are closed but the command
    # hasn't finished cleanup by the first poll() call
    while proc.poll() is None:
        time.sleep(1)

    if proc.poll() != 0:
        raise Exception("Return code: {}".format(proc.returncode))

def run(cmd):
    """Run the given command

    Note: This method will stream the results of the command to stdout
          so that for long running commands the results can be seen
          before the command finishes

    Args:
        cmd (str): The command to run

    Raises:
        Exception: If the return code is non-zero
    """
    # DP TODO: With a little massaging script and run could be merged into a single method
    print("----------------------------------------------------------------------------------")
    print(cmd)

    proc = subprocess.Popen(shlex.split(cmd),
                            bufsize=1, # line bufferred
                            stderr=subprocess.STDOUT,
                            stdout=subprocess.PIPE)

    for line in proc.stdout:
        print(line.decode('utf8'), end='', flush=True)


    # Verify that the command has finished cleaning up
    # sometime stdout/stderr are closed but the command
    # hasn't finished cleanup by the first poll() call
    while proc.poll() is None:
        time.sleep(1)

    if proc.poll() != 0:
        raise Exception("Return code: {}".format(proc.returncode))

if __name__ == '__main__':
    cur_dir = pathlib.Path(__file__).parent
    os.chdir(cur_dir)

    if len(sys.argv) != 3:
        print("Usage: {} <domain name> <bucket name>".format(sys.argv[0]))
        sys.exit(-1)

    domain = sys.argv[1]
    bucket = sys.argv[2]

    # Not all AWS Lambda containers have these libraries installed
    # verify that they are installed before importing them
    # (This can happen with non-python runtimes)
    # DP NOTE: using --user in case the script is not run as root
    #          this can sometimes result in an import error, though
    #          running the script again (after the packages have been
    #          installed) normally works
    run('python3 -m pip install --user boto3 PyYaml')
    import boto3
    import yaml

    zip_file = cur_dir / 'staging' / (domain + '.zip')
    staging_dir = cur_dir / 'staging' / domain

    # Remove the old build directory
    if staging_dir.exists():
        try:
            shutil.rmtree(staging_dir)
        except OSError:
            # DP NOTE: Sometimes rmtree fails with 'file busy' error for me
            run('rm -r {}'.format(staging_dir))

    staging_dir.mkdir()
    unzip(zip_file, staging_dir)
    starting_hash = script_stdout('find . -type f -print0 | sort -z | xargs -0 sha1sum | sha1sum').split()[0]

    lambda_config = load_config(staging_dir)

    # Check the current hash against the existing S3 object's hash
    # DP NOTE: This is done as rebuilding twice with the same input hash can result in two different results
    #          as if dependencies are not competely pinned then there may be a version change in a dependency
    s3 = boto3.session.Session().client('s3')
    try:
        target_name = lambda_config['name'] + '.' + domain + '.zip'
        resp = s3.head_object(Bucket = bucket, Key = target_name)
        metadata = resp['Metadata']
        if metadata['build-hash'] == starting_hash:
            print("Input hash matches existing S3 object, not rebuilding")
            sys.exit(0)
    except Exception:
        pass # If there was an error with the check just rebuild

    print("Building lambda")

    # Install System Packages
    if lambda_config.get('system_packages'):
        # DP NOTE: Expectation is that if no matter where run sudo will be able
        #          to prompt for password, if it is needed
        packages = ' '.join(lambda_config['system_packages'])
        cmd = 'yum install -y ' + packages
        if os.geteuid() != 0:
            cmd = 'sudo ' + cmd

        run(cmd)

    # Install Python Packages
    if lambda_config.get('python_packages'):
        cmd_req = 'python3 -m pip install -t {location} -r {requirements}'
        cmd_pkgs = 'python3 -m pip install -t {location} {packages}'

        entries = lambda_config['python_packages']
        if type(entries) == list: # list of packages, convert to the dict format with
                                  # the staging directory as the location to install
            entries = { entry : '.'
                        for entry in entries }

        packages = {}
        for entry in entries:
            if (staging_dir / entry).is_file(): # pointing to requirements file
                run(cmd_req.format(location = staging_dir / entries[entry],
                                   requirements = staging_dir / entry))
            elif (staging_dir / entry).is_dir(): # pointing to a local repository
                run(cmd_pkgs.format(location = staging_dir / entries[entry],
                                    packages = staging_dir / entry))
            else:
                location = entries[entry]
                if location not in packages:
                    packages[location] = []
                packages[location].append(entry)

        for loc, pkgs in packages.items():
            run(cmd_pkgs.format(location = staging_dir / loc,
                                packages = ' '.join(pkgs)))

    # Run Manual Commands
    if lambda_config.get('manual_commands'):
        for cmd in lambda_config['manual_commands']:
            script(cmd)

    target_name = lambda_config['name'] + '.' + domain
    if 'output_file' in lambda_config:
        # The lambda build process may create its own code zip, so use that instead
        output_file = staging_dir / lambda_config['output_file']
    else:
        # Automatically zip up all of the files in the build directory

        # Chmod the results, so that the lambda can access the files
        for path, _, files in os.walk(staging_dir):
            for filename in files:
                os.chmod(os.path.join(path, filename), 0o777)
        #run('chmod -R 0777 {staging_dir}')

        output_file = cur_dir / 'staging' / target_name
        output_file = shutil.make_archive(output_file, 'zip', staging_dir)
        output_file = pathlib.Path(output_file)

    target_name += '.zip' # shutil.make_archive request the name without extension

    # Extracted from boss-tools.git/lambdautils/deploy_lambdas.py as not all lambdas will zip up that file
    # to be included in the build process
    metadata = {'build-hash': starting_hash} # will become x-amz-meta-build-bash
    upload_to_s3(output_file, target_name, bucket, metadata)

    if lambda_config.get('is_layer', False):
        create_layer(bucket, target_name, starting_hash)

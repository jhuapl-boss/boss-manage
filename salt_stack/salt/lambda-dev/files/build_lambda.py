#!/usr/bin/env python3

import boto3
import os
import sys
import time
import glob
import yaml
import zipfile
import shlex
import shutil
import subprocess
import pathlib


def upload_to_s3(zip_file, target_name, bucket):
    """Upload the zip file to the given S3 bucket.

    Args:
        zip_file (Path): Name of zip file.  The name (after any path is stripped) is used as the key.
        target_name (string): Name to give the zip_File in S3
        bucket (string): Name of bucket to use.
    """
    session = boto3.session.Session()
    s3 = session.client('s3')
    try:
        s3.create_bucket(Bucket=bucket)
    except s3.exceptions.BucketAlreadyOwnedByYou:
        pass # Only us-east-1 will not throw an exception if the bucket already exists

    print("{} -> {}".format(zip_file, bucket))
    with zip_file.open('rb') as fh:
        s3.put_object(Bucket=bucket, Key=target_name, Body=fh)

def unzip(zippath, path):
    fzip = zipfile.ZipFile(zippath, 'r')
    fzip.extractall(path)

def load_config(staging_dir):
    with open(os.path.join(staging_dir, 'lambda.yml'), 'r') as fh:
        return yaml.load(fh.read())

def script(cmd):
    print("----------------------------------------------------------------------------------")
    print(cmd)

    env = os.environ.copy()
    env['STAGING_DIR'] = staging_dir

    proc = subprocess.Popen(['/bin/bash'],
                            env=env,
                            cwd=staging_dir,
                            bufsize=1, # line bufferred
                            #universal_newlines=True, # so we don't have to encode/decode
                            stderr=subprocess.STDOUT,
                            stdout=subprocess.PIPE,
                            stdin=subprocess.PIPE)

    proc.stdin.write(cmd.encode())
    proc.stdin.close()

    for line in proc.stdout:
        print(line.decode('utf8'), end='', flush=True)

    while proc.poll() is None:
        time.sleep(1)

    if proc.poll() != 0:
        raise Exception("Return code: {}".format(proc.returncode))

def run(cmd):
    print("----------------------------------------------------------------------------------")
    print(cmd)

    proc = subprocess.Popen(shlex.split(cmd),
                            bufsize=1, # line bufferred
                            #universal_newlines=True, # so we don't have to encode/decode
                            stderr=subprocess.STDOUT,
                            stdout=subprocess.PIPE)

    for line in proc.stdout:
        print(line.decode('utf8'), end='', flush=True)

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

    zip_file = cur_dir / 'staging' / (domain + '.zip')
    staging_dir = cur_dir / 'staging' / domain

    if staging_dir.exists():
        try:
            shutil.rmtree(staging_dir)
        except OSError:
            # DP NOTE: Sometimes rmtree fails with 'file busy' error for me
            run('rm -r {}'.format(staging_dir))

    staging_dir.mkdir()
    unzip(zip_file, staging_dir)

    print("Building lambda")

    lambda_config = load_config(staging_dir)

    # Install System Packages
    if 'system_packages' in lambda_config:
        packages = ' '.join(lambda_config['system_packages'])
        cmd = 'yum install -y ' + packages

        run(cmd)

    # Install Python Packages
    if 'python_packages' in lambda_config:
        packages = []
        cmd = 'pip3 install -t {} -r {{}}'.format(staging_dir)
        for entry in lambda_config['python_packages']:
            if (staging_dir / entry).exists():
                run(cmd.format(staging_dir / entry))
            else:
                packages.append(entry)

        if len(packages) > 0:
            cmd = 'pip3 install -t {} {}'.format(staging_dir, ' '.join(packages))
            run(cmd)

    # Run Manual Commands
    if 'manual_commands' in lambda_config:
        for cmd in lambda_config['manual_commands']:
            script(cmd)

    target_name = lambda_config['name'] + '.' + domain
    if 'output_file' in lambda_config:
        output_file = staging_dir / lambda_config['output_file']
    else:
        # Chmod the results
        for path, _, files in os.walk(staging_dir):
            for filename in files:
                os.chmod(os.path.join(path, filename), 0o777)
        #run('chmod -R 0777 {staging_dir}')

        output_file = cur_dir / 'staging' / target_name
        output_file = shutil.make_archive(output_file, 'zip', staging_dir)

    target_name += '.zip' # shutil.make_archive request the name without extension

    # Extracted from boss-tools.git/lambdautils/deploy_lambdas.py as not all lambdas will zip up that file
    # to be included in the build process
    upload_to_s3(output_file, target_name, bucket)

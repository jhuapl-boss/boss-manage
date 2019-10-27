#!/usr/bin/env python3

import os
import sys
import glob
import yaml
import zipfile
import shutil
import subprocess
import pathlib



def unzip(zippath, path):
    fzip = zipfile.ZipFile(zippath, 'r')
    fzip.extractall(path)

def load_config(staging_dir):
    with open(os.path.join(staging_dir, 'lambda.yml'), 'r') as fh:
        return yaml.load(fh.read())

def run(cmd):
    print("----------------------------------------------------------------------------------")
    print(cmd)

    env = os.environ.copy()
    env['STAGING_DIR'] = staging_dir

    proc = subprocess.Popen(['/bin/bash'],
                            env=env,
                            stderr=subprocess.STDOUT,
                            stdout=subprocess.PIPE,
                            stdin=subprocess.PIPE)

    cmd = cmd.encode()
    while proc.poll() is None:
        try:
            stdout, _ = proc.communicate(input=cmd,
                                         timeout=10)
            print(stdout.decode('utf-8'), end='', flush=True)
        except subprocess.TimeoutExpired:
            pass
        cmd = None

    if proc.returncode != 0:
        raise Exception()

if __name__ == '__main__':
    cur_dir = pathlib.Path(__file__).parent
    print(cur_dir)
    os.chdir(cur_dir)

    print(sys.argv)
    if len(sys.argv) != 3:
        print("Usage: {} <domain name> <bucket name>".format(sys.argv[0]))
        sys.exit(-1)

    stdout = subprocess.check_output('ls -la', shell=True)
    print(stdout.decode('utf-8'))
    stdout = subprocess.check_output('ls -la staging', shell=True)
    print(stdout.decode('utf-8'))
    stdout = subprocess.check_output('whoami', shell=True)
    print(stdout.decode('utf-8'))

    domain = sys.argv[1]
    bucket = sys.argv[2]

    zip_file = cur_dir / 'staging' / (domain + '.zip')
    staging_dir = cur_dir / 'staging' / domain

    if staging_dir.exists():
        try:
            shutil.rmtree(staging_dir)
        except OSError:
            # DP NOTE: Sometimes rmtree fails with 'file busy' error for me
            subprocess.check_output('rm -r {}'.format(staging_dir), shell=True)
    staging_dir.mkdir()
    unzip(zip_file, staging_dir)

    print("Building lambda")

    for filename in staging_dir.glob('*'):
        print("- {}".format(filename))

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
            if os.path.exists(entry):
                run(cmd.format(entry))
            else:
                packages.append(entry)
        cmd = 'pip3 install -t {} {}'.format(staging_dir, ' '.join(packages))
        run(cmd)

    # Run Manual Commands
    if 'manual_commands' in lambda_config:
        for cmd in lambda_config['manual_commands']:
            run(cmd)

    # TODO zip up staging directory

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

"""Script for building BOSS VM images using Packer.

Script that creates a simple interface (with minimal commandline arguments) for
building VM images using Packer and SaltStack.

Author:
    Derek Pryor <Derek.Pryor@jhuapl.edu>
"""

import argparse
import sys
import os
import glob
import json
import yaml
import shlex
import subprocess
import configparser
from distutils.spawn import find_executable
from boto3.session import Session

import alter_path
from lib.constants import repo_path
from lib import configuration
from lib import utils

CONFIGS = [
    "activities",
    "auth",
    "backup",
    "cachemanager",
    "endpoint",
    "vault",
]

os.environ["PATH"] += ":" + repo_path("bin") # allow executing Packer from the bin/ directory

def lambda_ami():
    # Amazon Linux AMI 2018.03.0 (HVM), SSD Volume Type
    # Should match runtime used by AWS Lambda
    #    https://docs.aws.amazon.com/lambda/latest/dg/lambda-runtimes.html
    # NOTE: The boss-manage code assumes that this will be an Amazon AMI
    #       that uses the 'ec2-user' user account
    return "ami-0080e4c5bc078760e"

def get_commit():
    """Figure out the commit hash of the current git revision.
        Note: Only works if the CWD is a git repository
    Returns:
        (string) : The git commit hash
    """
    cmd = "git rev-parse HEAD"
    result = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE)
    return result.stdout.decode("utf-8").strip()

def execute(cmd, output_file, env={}):
    """Execuit the given command and redirect STDOUT and STDERR to output_file.
    Args:
        cmd (string) : Command to execute
        outpout_file (string) : Name of file to redirect output to
    Returns:
        (Popen) : Popen object representing the executing command
    """
    return subprocess.Popen(shlex.split(cmd),
                            stderr=subprocess.STDOUT,
                            stdout=open(output_file, "w"),
                            env = dict(os.environ, **env))

def locate_ami(session):
    def contains(x, ys):
        for y in ys:
            if y not in x:
                return False
        return True

    client = session.client('ec2')
    response = client.describe_images(
        Filters=[
            {"Name": "virtualization-type", "Values": ["hvm"]},
            {"Name": "root-device-type", "Values": ["ebs"]},
            {"Name": "architecture", "Values": ["x86_64"]},
        ],
        # Owner: AWS: 679593333241
        # Owner: Canonical: 099720109477
        Owners=['099720109477'])

    images = response['Images']
    #images = [i for i in images if contains(i['Name'], ('hvm-ssd', '14.04', 'server'))]
    images = [i for i in images if contains(i['Name'], ('hvm-ssd', '20.04', 'server'))]
    images.sort(key=lambda x: x["CreationDate"], reverse=True)

    if len(images) == 0:
        print("Error: could not locate base AMI, exiting ....")
        sys.exit(1)

    print("Using {}".format(images[0]['Name']))
    return images[0]['ImageId']

if __name__ == '__main__':
    for cmd in ("git", "packer"):
        if find_executable(cmd) is None:
            print("Could not locate {} binary on the system, required...".format(cmd))
            sys.exit(1)

    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    git_hash = get_commit()

    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    # Use a seperate top level key in top.sls for AMIs?
    # Use a seperate top level key to say which AMIs to not build using packer.py
    #config_file = repo_path("salt_stack", "salt", "top.sls")
    #with open(config_file, 'r') as fh:
    #    top = yaml.load(fh.read())
    #    configs = [k for k in top['base']]
    #    print(configs)

    config_help_names = list(CONFIGS)
    config_help_names.append("all")
    config_help_names.append("lambda")
    config_help = create_help("config is on of the following: ('all' will build all except 'lambda' and 'backup')", config_help_names)

    parser = configuration.BossParser(description = "Script the building of machines images using Packer and SaltStack",
                                      formatter_class=argparse.RawDescriptionHelpFormatter,
                                      epilog=config_help)
    parser.add_argument("--single-thread",
                        action = "store_true",
                        default = False,
                        help = "Only build one config at a time. (default: Build all configs at the same time)")
    parser.add_argument("--force", "-f",
                        action = "store_true",
                        default = False,
                        help = "Override any existing AMI with the same name")
    parser.add_argument("--ami-version",
                        metavar = "<ami-version>",
                        default = 'h' + git_hash[:8],
                        help = "The AMI version for the machine image(s). (default: First 8 characters of the git SHA1 hash)")
    parser.add_argument("--base-ami",
                        metavar = "<base-ami>",
                        help = "Base AMI to build the new Image from")
    parser.add_bosslet()
    parser.add_argument("config",
                        choices = config_help_names,
                        metavar = "<config>",
                        nargs = "+",
                        help="Packer variable to build a machine image for")
    args = parser.parse_args()

    if "all" in args.config:
        args.config = ["activities", "auth", "cachemanager", "endpoint", "vault"]  # All but backup and lambda

    if args.bosslet_config.OUTBOUND_BASTION:
        bastion_config = """-var 'aws_bastion_ip={}'
                            -var 'aws_bastion_port={}'
                            -var 'aws_bastion_user={}'
                            -var 'aws_bastion_priv_key_file={}'
                         """.format(args.bosslet_config.OUTBOUND_IP,
                                    args.bosslet_config.OUTBOUND_PORT,
                                    args.bosslet_config.OUTBOUND_USER,
                                    utils.keypair_to_file(args.bosslet_config.OUTBOUND_KEY))
    else:
        bastion_config = ""

    env_vars = {}
    aws_profile = args.bosslet_config.PROFILE
    if aws_profile is not None:
        env_vars['AWS_PROFILE'] = aws_profile

    packer_file = repo_path("packer", "vm.packer")

    packer_logs = repo_path("packer", "logs")
    if not os.path.isdir(packer_logs):
        os.mkdir(packer_logs)

    if args.base_ami:
        ami = args.base_ami
    else:
        ami = locate_ami(args.bosslet_config.session)

    cmd = """{packer} build
             {bastion}
             -var 'name={machine}' -var 'ami_version={ami_version}'
             -var 'ami_suffix={ami_suffix}' -var 'aws_region={region}'
             -var 'commit={commit}' -var 'force_deregister={deregister}'
             -var 'aws_source_ami={ami}' -var 'aws_source_user={user}'
             {packer_file}"""
    cmd_args = {
        "packer" : "packer",
        "bastion" : bastion_config,
        "packer_file" : packer_file,
        "region": args.bosslet_config.REGION,
        "ami_suffix": args.bosslet_config.AMI_SUFFIX,
        "ami_version" : ("-" + args.ami_version) if len(args.ami_version) > 0 else "",
        "commit" : git_hash,
        "ami" : ami,
        "user": "ubuntu",
        "deregister" : "true" if args.force else "false",
        "machine" : "" # replace for each call
    }

    procs = []
    for config in args.config:
        print("Launching {} configuration".format(config))
        log_file = os.path.join(packer_logs, config + ".log")
        cmd_args["machine"] = config
        cmd_args['ami'] = lambda_ami() if config == 'lambda' else ami
        cmd_args['user'] = 'ec2-user' if config == 'lambda' else 'ubuntu'

        proc = execute(cmd.format(**cmd_args), log_file, env_vars)

        if args.single_thread:
            print("Waiting for build to finish")
            proc.wait()
        else:
            procs.append(proc)

    try:
        print("Waiting for all builds started to finish")
        for proc in procs:
            proc.wait()
    except KeyboardInterrupt: # <CTRL> + c
        print("Killing builds")
        for proc in procs:
            proc.poll()
            if proc.returncode is None:
                proc.kill()

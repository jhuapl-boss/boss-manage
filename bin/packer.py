#!/usr/bin/env python3.5
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
    "consul",
    "endpoint",
    "vault",
]

os.environ["PATH"] += ":" + repo_path("bin") # allow executing Packer from the bin/ directory

def get_commit():
    """Figure out the commit hash of the current git revision.
        Note: Only works if the CWD is a git repository
    Returns:
        (string) : The git commit hash
    """
    cmd = "git rev-parse HEAD"
    result = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE)
    return result.stdout.decode("utf-8").strip()

def execute(cmd, output_file):
    """Execuit the given command and redirect STDOUT and STDERR to output_file.
    Args:
        cmd (string) : Command to execute
        outpout_file (string) : Name of file to redirect output to
    Returns:
        (Popen) : Popen object representing the executing command
    """
    return subprocess.Popen(shlex.split(cmd), stderr=subprocess.STDOUT, stdout=open(output_file, "w"))

def locate_ami(session):
    def contains(x, ys):
        for y in ys:
            if y not in x:
                return False
        return True

    client = session.client('ec2')
    response = client.describe_images(Filters=[
                    {"Name": "owner-id", "Values": ["099720109477"]},
                    {"Name": "virtualization-type", "Values": ["hvm"]},
                    {"Name": "root-device-type", "Values": ["ebs"]},
                    {"Name": "architecture", "Values": ["x86_64"]},
                    #{"Name": "platform", "Values": ["Ubuntu"]},
                    #{"Name": "name", "Values": ["hvm-ssd"]},
                    #{"Name": "name", "Values": ["14.04"]},
               ])

    images = response['Images']
    images = [i for i in images if contains(i['Name'], ('hvm-ssd', '14.04', 'server'))]
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

    config_glob = repo_path("packer", "variables", "*")
    config_help_names = list(CONFIGS)
    config_help_names.append("all")
    config_help = create_help("config is on of the following:", config_help_names)

    parser = argparse.ArgumentParser(description = "Script the building of machines images using Packer and SaltStack",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=config_help)
    parser.add_argument("--single-thread",
                        action = "store_true",
                        default = False,
                        help = "Only build one config at a time. (default: Build all configs at the same time)")
    parser.add_argument("--only",
                        metavar = "<packer-builder>",
                        default = "amazon-ebs",
                        help = "Which Packer building to use. (default: amazon-ebs)")
    parser.add_argument("--force", "-f",
                        action = "store_true",
                        default = False,
                        help = "Override any existing AMI with the same name")
    parser.add_argument("--ami-version",
                        metavar = "<ami-version>",
                        default = 'h' + git_hash[:8],
                        help = "The AMI version for the machine image(s). (default: First 8 characters of the git SHA1 hash)")
    parser.add_argument("bosslet_name",
                        help="Bosslet in which to execute the build")
    parser.add_argument("config",
                        choices = config_help_names,
                        metavar = "<config>",
                        nargs = "+",
                        help="Packer variable to build a machine image for")

    args = parser.parse_args()

    if not configuration.valid_bosslet(args.bosslet_name):
        parser.print_usage()
        print("Error: Bosslet name '{}' doesn't exist in configs file ({})".format(args.bosslet_name, configuration.CONFIGS_PATH))
        sys.exit(1)

    bosslet_config = configuration.BossConfiguration(args.bosslet_name)

    if "all" in args.config:
        args.config = CONFIGS

    if bosslet_config.OUTBOUND_BASTION:
        bastion_config = """-var 'aws_bastion_ip={}'
                            -var 'aws_bastion_user={}'
                            -var 'aws_bastion_priv_key_file={}'
                         """.format(bosslet_config.OUTBOUND_IP,
                                    bosslet_config.OUTBOUND_USER,
                                    utils.keypair_to_file(bosslet_config.OUTBOUND_KEY))
    else:
        bastion_config = ""

    aws_creds = bosslet_config.session.get_credentials()
    credentials_config = repo_path("config", "aws-credentials")
    credentials_config = """-var 'aws_access_key={}'
                            -var 'aws_secret_key={}'
                         """.format(aws_creds.access_key,
                                    aws_creds.secret_key)

    packer_file = repo_path("packer", "vm.packer")

    packer_logs = repo_path("packer", "logs")
    if not os.path.isdir(packer_logs):
        os.mkdir(packer_logs)

    ami = locate_ami(bosslet_config.session)

    cmd = """{packer} build
             {bastion} {credentials}
             -var 'name={machine}' -var 'ami_version={ami_version}'
             -var 'ami_suffix={ami_suffix}' -var 'aws_region={region}'
             -var 'commit={commit}' -var 'force_deregister={deregister}'
             -var 'aws_source_ami={ami}' -only={only} {packer_file}"""
    cmd_args = {
        "packer" : "packer",
        "bastion" : bastion_config,
        "credentials" : credentials_config,
        "only" : args.only,
        "packer_file" : packer_file,
        "region": bosslet_config.REGION,
        "ami_suffix": bosslet_config.AMI_SUFFIX,
        "ami_version" : "-" + args.ami_version,
        "commit" : git_hash,
        "ami" : ami,
        "deregister" : "true" if args.force else "false",
        "machine" : "" # replace for each call
    }

    procs = []
    for config in args.config:
        print("Launching {} configuration".format(config))
        log_file = os.path.join(packer_logs, config + ".log")
        cmd_args["machine"] = config
        proc = execute(cmd.format(**cmd_args), log_file)

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

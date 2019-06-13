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

"""A script for looking up the IP address of an AWS instance and then starting
an SSH session with the machine.

Environmental Variables:
    AWS_CREDENTIALS : File path to a JSON encode file containing the following keys
                      "aws_access_key" and "aws_secret_key"
    SSH_KEY : File path to a SSH private key, protected as required by SSH,
              (normally this means that the private key is only readable by the user)
    BASTION_IP : IP / public DNS name of a bastion server that all SSH traffic
                 needs to be routed through
    BASTION_KEY : Same as SSH_KEY, but it is the SSH private key for the bastion server
    BASTION_USER : The user account on the bastion server to use when creating the tunnel
                   The BASTION_USER should be accessable via BASTION_KEY

Author:
    Derek Pryor <Derek.Pryor@jhuapl.edu>
"""

import argparse
import os
import sys

import alter_path
from lib import utils
from lib import aws
from lib import configuration
from lib.ssh import SSHConnection, SSHTarget
from lib.names import AWSNames
from lib.utils import keypair_to_file

if __name__ == "__main__":
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    parser = configuration.BossParser(description = "Script to lookup AWS instance names and start an SSH session",
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cmd", "-c",
                        default=None,
                        help="command to run in ssh, if you want to run a command.")
    parser.add_argument("--scp",
                        default=None,
                        help="Copy file. (Format: 'remote:path local:path' or 'local:path remote:path')")
    parser.add_argument("--user", "-u",
                        default=None,
                        help="username on remote host.")
    parser.add_argument("--key", "-k",
                        default=None,
                        help="SSH keypair name for the instance (Default: bosslet.SSH_KEY)")
    parser.add_hostname(private_ip = True)

    args = parser.parse_args()

    # the bastion server (being an AWS AMI) has a differnt username
    if args.user is None:
        user = "ec2-user" if args.hostname.startswith("bastion") else "ubuntu"
    else:
        user = args.user

    if args.bosslet_config.outbound_bastion:
        bastions = [args.bosslet_config.outbound_bastion]
    else:
        bastions = []

    ssh_key = keypair_to_file(args.key) if args.key else args.bosslet_config.ssh_key
    ssh_target = SSHTarget(ssh_key, args.ip, 22, user)
    ssh = SSHConnection(ssh_target, bastions)
    if args.cmd:
        ret = ssh.cmd(args.cmd)
    if args.scp:
        a,b = args.scp.split()
        t_a, a = a.split(":")
        t_b, b = b.split(":")
        scp_args = {
            t_a.lower() + '_file': a,
            t_b.lower() + '_file': b,
            'upload': t_a.lower() == "local"
        }
        ret = ssh.scp(**scp_args)
    else:
        ret = ssh.shell()
    sys.exit(ret)

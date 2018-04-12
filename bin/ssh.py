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

if __name__ == "__main__":
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    parser = argparse.ArgumentParser(description = "Script to lookup AWS instance names and start an SSH session",
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
    parser.add_argument("--bosslet", "-b",
                        default=None,
                        help="Bosslet in which the machine is running")
    parser.add_argument("--private-ip", "-p",
                        action='store_true',
                        default=False,
                        help="add this flag to type in a private IP address in internal command instead of a DNS name which is looked up")
    parser.add_argument("hostname", help="Hostname of the EC2 instance to create SSH Tunnels on")

    args = parser.parse_args()

    if args.private_ip and not args.bosslet:
        parser.print_usage()
        print("Error: --bosslet required if --private-ip is used")
        sys.exit(1)

    if not args.private_ip:
        idx, machine, bosslet_name = utils.parse_hostname(args.hostname)

        if not bosslet_name and not args.bosslet:
            parser.print_usage()
            print("Error: could not parse out bosslet name, use --bosslet")
            sys.exit(1)

        # hande explicit bosslet
        if args.bosslet:
            bosslet_name = args.bosslet

        if not configuration.valid_bosslet(bosslet_name):
            parser.print_usage()
            print("Error: Bosslet name '{}' doesn't exist in configs file ({})".format(bosslet_name, configuration.CONFIGS_PATH))
            sys.exit(1)

        # convert machine to hostname
        bosslet_config = configuration.BossConfiguration(bosslet_name)
        names = AWSNames(bosslet_config)
        hostname = names.dns[machine]
        if idx is not None:
            hostname = str(idx) + "." + hostname # re-add the index value

        # lookup hostname in aws
        ip = aws.machine_lookup(bosslet_config.session, hostname)
        if not ip:
            sys.exit(1) # error message already printed
    else:
        ip = args.hostname
        bosslet_name = args.bosslet

        if not configuration.valid_bosslet(bosslet_name):
            parser.print_usage()
            print("Error: Bosslet name '{}' doesn't exist in configs file ({})".format(bosslet_name, configuration.CONFIGS_PATH))
            sys.exit(1)

        bosslet_config = configuration.BossConfiguration(bosslet_name)

    # the bastion server (being an AWS AMI) has a differnt username
    if args.user is None:
        user = "ec2-user" if args.hostname.startswith("bastion") else "ubuntu"
    else:
        user = args.user

    if bosslet_config.outbound_bastion:
        bastions = [bosslet_config.outbound_bastion]
    else:
        bastions = []

    ssh_target = SSHTarget(bosslet_config.ssh_key, ip, 22, user)
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

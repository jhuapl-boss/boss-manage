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
from lib import aws
from lib.ssh import SSHConnection

if __name__ == "__main__":
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    parser = argparse.ArgumentParser(description = "Script to lookup AWS instance names and start an SSH session",
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aws-credentials", "-a",
                        metavar = "<file>",
                        default = os.environ.get("AWS_CREDENTIALS"),
                        type = argparse.FileType('r'),
                        help = "File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("--ssh-key", "-s",
                        metavar = "<file>",
                        default = os.environ.get("SSH_KEY"),
                        help = "SSH private key to use when connecting to AWS instances (default: SSH_KEY)")
    parser.add_argument("--cmd", "-c",
                        default=None,
                        help="command to run in ssh, if you want to run a command.")
    parser.add_argument("--scp",
                        default=None,
                        help="Copy file. (Format: 'remote:path local:path' or 'local:path remote:path')")
    parser.add_argument("hostname", help="Hostname of the EC2 instance to create SSH Tunnels on")
    parser.add_argument("--user", "-u",
                        default=None,
                        help="username on remote host.")
    parser.add_argument("--private-ip", "-p",
                        action='store_true',
                        default=False,
                        help="add this flag to type in a private IP address in internal command instead of a DNS name which is looked up")

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)
    if args.ssh_key is None:
        parser.print_usage()
        print("Error: SSH key not provided and SSH_KEY is not defined")
        sys.exit(1)
    if not os.path.exists(args.ssh_key):
        parser.print_usage()
        print("Error: SSH key '{}' does not exist".format(args.ssh_key))
        sys.exit(1)

    session = aws.create_session(args.aws_credentials)
    if args.private_ip:
        ip = args.hostname
    else:
        ip = aws.machine_lookup(session, args.hostname)

    # the bastion server (being an AWS AMI) has a differnt username
    if args.user is None:
        user = "ec2-user" if args.hostname.startswith("bastion") else "ubuntu"
    else:
        user = args.user

    ssh = SSHConnection(args.ssh_key, (ip, 22, user))
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

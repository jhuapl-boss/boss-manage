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

"""A script to forming a tunnel to a bastion host and then connecting to an
internal machine from the bastion host.

Note: There are two Bastion machines talked about by this script.
      * The first is the bastion specified on the command line and is associated
        with the target VPC. This bastion allows internal access to private VPC
        resources.
      * The second is the bastion specified in environmental variables and is
        to form external SSH connections. This is an optional bastion and was
        put into place to help deal with corporate firewalls that limit outgoing
        SSH connections.

SSH_OPTIONS : Extra command line options that are passed to every SSH call

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

import vault

import alter_path
from lib import aws
from lib.ssh import SSHConnection, vault_tunnel
from lib.vault import Vault

if __name__ == "__main__":
    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    commands = ["ssh", "scp", "ssh-cmd", "ssh-tunnel", "ssh-all"]
    commands.extend(vault.COMMANDS.keys())
    commands_help = create_help("command supports the following:", commands)

    parser = argparse.ArgumentParser(description = "Script creating SSH Tunnels and connecting to internal VMs",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=commands_help)


    parser.add_argument("--aws-credentials", "-a",
                        metavar = "<file>",
                        default = os.environ.get("AWS_CREDENTIALS"),
                        type = argparse.FileType('r'),
                        help = "File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("--private-ip", "-p",
                        action='store_true',
                        default=False,
                        help = "add this flag to type in a private IP address in internal command instead of a DNS name which is looked up")
    parser.add_argument("--user", "-u",
                        default='ubuntu',
                        help = "Username of the internal machine")
    parser.add_argument("--port",
                        default=22,
                        type=int,
                        help = "Port to connect to on the internal machine")
    parser.add_argument("--ssh-key", "-s",
                        metavar = "<file>",
                        default = os.environ.get("SSH_KEY"),
                        help = "SSH private key to use when connecting to AWS instances (default: SSH_KEY)")
    parser.add_argument("--bastion","-b",  help="Hostname of the EC2 bastion server to create SSH Tunnels on")
    parser.add_argument("internal", help="Hostname of the EC2 internal server to create the SSH Tunnels to")
    parser.add_argument("command",
                        choices = commands,
                        metavar = "command",
                        help = "Command to execute")
    parser.add_argument("arguments",
                        nargs = "*",
                        help = "Arguments to pass to the command")

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

    # This next step will make bastion work with 1.consul or 1.vault internal names.
    boss_position = 1
    try:
        int(args.internal.split(".", 1)[0])
        boss_position = 2
    except ValueError:
        pass

    bastion_host = args.bastion if args.bastion else "bastion." + args.internal.split(".", boss_position)[boss_position]
    bastion = aws.machine_lookup(session, bastion_host)
    if args.private_ip:
        private = args.internal
    else:
        private = aws.machine_lookup(session, args.internal, public_ip=False)

    ssh = SSHConnection(args.ssh_key, (private, args.port, args.user), bastion)

    if args.command in ("ssh",):
        ssh.shell()
    elif args.command in ("scp",):
        ret = ssh.scp(*args.arguments)
        sys.exit(ret)
    elif args.command in ("ssh-cmd",):
        ret = ssh.cmd(*args.arguments)
        sys.exit(ret)
    elif args.command in ("ssh-tunnel",):
        ssh.external_tunnel(*args.arguments)
    elif args.command in ("ssh-all",):
        addrs = aws.machine_lookup_all(session, args.internal, public_ip=False)
        for addr in addrs:
            print("{} at {}".format(args.internal, addr))
            ssh = SSHConnection(args.ssh_key, addr, bastion)
            ssh.cmd(*args.arguments)
            print()
    elif args.command in vault.COMMANDS:
        with vault_tunnel(args.ssh_key, bastion):
            vault.COMMANDS[args.command](Vault(args.internal, private), *args.arguments)
    else:
        parser.print_usage()
        sys.exit(1)

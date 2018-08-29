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

import os
import sys
import argparse

import vault

import alter_path
from lib import aws
from lib import utils
from lib import configuration
from lib.ssh import SSHConnection, SSHTarget, vault_tunnel
from lib.vault import Vault

if __name__ == "__main__":
    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    commands = ["ssh", "scp", "ssh-cmd", "ssh-tunnel", "ssh-all"]
    commands.extend(vault.COMMANDS.keys())
    commands_help = create_help("command supports the following:", commands)

    parser = configuration.BossParser(description = "Script creating SSH Tunnels and connecting to internal VMs",
                                      formatter_class=argparse.RawDescriptionHelpFormatter,
                                      epilog=commands_help)

    parser.add_hostname(private_ip = True)
    parser.add_argument("--user", "-u",
                        default='ubuntu',
                        help = "Username of the internal machine")
    parser.add_argument("--port",
                        default=22,
                        type=int,
                        help = "Port to connect to on the internal machine")
    parser.add_argument("--local-port",
                        default = None,
                        type = int,
                        help = "Local port to use when tunneling")
    parser.add_argument("command",
                        choices = commands,
                        metavar = "command",
                        help = "Command to execute")
    parser.add_argument("arguments",
                        nargs = "*",
                        help = "Arguments to pass to the command")

    args = parser.parse_args()
    bosslet_config = args.bosslet_config

    bastion = aws.machine_lookup(bosslet_config.session,
                                 bosslet_config.names.dns.bastion) 

    ssh_target = SSHTarget(bosslet_config.ssh_key, args.ip, args.port, args.user)
    bastions = [SSHTarget(bosslet_config.ssh_key, bastion, 22, 'ec2-user')]
    if bosslet_config.outbound_bastion:
        bastions.insert(0, bosslet_config.outbound_bastion)
    ssh = SSHConnection(ssh_target, bastions, args.local_port)

    if args.command in ("ssh",):
        ssh.shell()
    elif args.command in ("scp",):
        ret = ssh.scp(*args.arguments)
        sys.exit(ret)
    elif args.command in ("ssh-cmd",):
        ret = ssh.cmd(*args.arguments)
        sys.exit(ret)
    elif args.command in ("ssh-tunnel",):
        with ssh.tunnel() as local_port:
            print("Connect to localhost:{} to be forwarded to {}:{}".format(local_port, args.ip, args.port))
            input("Waiting to close tunnel...")
    elif args.command in ("ssh-all",):
        addrs = aws.machine_lookup_all(bosslet_config.session, hostname, public_ip=False)
        for addr in addrs:
            print("{} at {}".format(hostname, addr))
            ssh_target = SSHTarget(bosslet_config.ssh_key, ip, args.port, args.user)
            ssh = SSHConnection(ssh_target, bastions)
            ssh.cmd(*args.arguments)
            print()
    elif args.command in vault.COMMANDS:
        with vault_tunnel(bosslet_config.ssh_key, bastions):
            vault.COMMANDS[args.command](Vault(args.internal, ip), *args.arguments)
    else:
        parser.print_usage()
        sys.exit(1)

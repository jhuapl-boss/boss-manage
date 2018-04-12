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
from lib import utils
from lib import configuration
from lib.ssh import SSHConnection, SSHTarget, vault_tunnel
from lib.names import AWSNames
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
    parser.add_argument("--bosslet",
                        default=None,
                        help="Bosslet in which the machine and bastion are running")
    parser.add_argument("internal", help="Hostname of the EC2 internal server to create the SSH Tunnels to")
    parser.add_argument("command",
                        choices = commands,
                        metavar = "command",
                        help = "Command to execute")
    parser.add_argument("arguments",
                        nargs = "*",
                        help = "Arguments to pass to the command")

    args = parser.parse_args()

    if args.private_ip and not args.bosslet:
        parser.print_usage()
        print("Error: --bosslet required if --private-ip is used")
        sys.exit(1)

    if not args.private_ip:
        idx, machine, bosslet_name = utils.parse_hostname(args.internal)

        if not bosslet_name and not args.bosslet:
            parser.print_usage()
            print("Error: could nto parse out bosslet name, use --bosslet")
            sys.exit(1)

        if args.bosslet:
            bosslet_name = args.bosslet

        if not configuration.valid_bosslet(bosslet_name):
            parser.print_usage()
            print("Error: Bosslet name '{}' doesn't exist in configs file ({})".format(bosslet_name, configuration.CONFIGS_PATH))
            sys.exit(1)

        bosslet_config = configuration.BossConfiguration(bosslet_name)
        names = AWSNames(bosslet_config)
        hostname = names.dns[machine]
        if idx is not None:
            hostname = str(idx) + "." + hostname
        ip = aws.machine_lookup(bosslet_config.session, hostname, public_ip=False)
        if not ip:
            sys.exit(1)
    else:
        ip = args.internal
        bosslet_name = args.bosslet

        if not configuration.valid_bosslet(bosslet_name):
            parser.print_usage()
            print("Error: Bosslet name '{}' doesn't exist in configs file ({})".format(bosslet_name, configuration.CONFIGS_PATH))
            sys.exit(1)

        bosslet_config = configuration.BossConfiguration(bosslet_name)
        names = AWSNames(bosslet_config)

    bastion = aws.machine_lookup(bosslet_config.session, names.dns.bastion) 

    ssh_target = SSHTarget(bosslet_config.ssh_key, ip, args.port, args.user)
    bastions = [SSHTarget(bosslet_config.ssh_key, bastion, 22, 'ec2-user')]
    if bosslet_config.outbound_bastion:
        bastions.insert(0, bosslet_config.outbound_bastion)
    ssh = SSHConnection(ssh_target, bastions)

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
        addrs = aws.machine_lookup_all(bosslet_config.session, hostname, public_ip=False)
        for addr in addrs:
            print("{} at {}".format(hostname, addr))
            ssh_target = SSHTarget(bosslet_config.ssh_key, ip, args.port, args.user)
            ssh = SSHConnection(ssh_target, bastions)
            ssh.cmd(*args.arguments)
            print()
    elif args.command in vault.COMMANDS:
        with vault_tunnel(bosslet_config.ssh_key, bastions):
            vault.COMMANDS[args.command](Vault(args.internal, private), *args.arguments)
    else:
        parser.print_usage()
        sys.exit(1)

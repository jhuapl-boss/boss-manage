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

"""A script to forming a tunnel to a bastion host and then connecting to an
internal machine from the bastion host.

SSH_OPTIONS - Extra command line options that are passed to every SSH call
"""

import argparse
import subprocess
import shlex
import os
import signal
import sys
import time
import random
from boto3.session import Session
import json
import vault

# Needed to prevent ssh from asking about the fingerprint from new machines
SSH_OPTIONS = "-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -q"

def create_tunnel(key, local_port, remote_ip, remote_port, bastion_ip, bastion_user="ec2-user", bastion_port=22):
    """Create a regular SSH tunnel from localhost:local_port to remote_ip:remote_port through bastion_ip."""
    fwd_cmd_fmt = "ssh -i {} {} -N -L {}:{}:{} -p {} {}@{}"
    fwd_cmd = fwd_cmd_fmt.format(key,
                                 SSH_OPTIONS,
                                 local_port,
                                 remote_ip,
                                 remote_port,
                                 bastion_port,
                                 bastion_user,
                                 bastion_ip)

    proc = subprocess.Popen(shlex.split(fwd_cmd))
    time.sleep(5) # wait for the tunnel to be setup
    return proc

def create_tunnel_aplnis(key, local_port, remote_ip, remote_port, bastion_ip, bastion_user="ec2-user"):
    """Read environmental variables to either directly connect to the given
    bastion_ip or use the given (second) bastion server as the first machine to
    connect to and route other tunnels through.

    This was added to support using a single machine given access through the
    APL firewall and tunnel all SSH connections through it.
    """
    apl_bastion_ip = os.environ.get("BASTION_IP")
    apl_bastion_key = os.environ.get("BASTION_KEY")
    apl_bastion_user = os.environ.get("BASTION_USER")

    if apl_bastion_ip is None or apl_bastion_key is None or apl_bastion_user is None:
        # traffic
        # localhost -> bastion -> remote
        print("APL Bastion information not defined, connecting directly")
        return create_tunnel(key, local_port, remote_ip, remote_port, bastion_ip, bastion_user)
    else:
        # traffic
        # localhost -> apl_bastion -> bastion -> remote
        print("Using APL Bastion host at {}".format(apl_bastion_ip))
        wrapper = ProcWrapper()
        port = locate_port()

        # Used http://superuser.com/questions/96489/ssh-tunnel-via-multiple-hops mssh.pl
        # to figure out the multiple tunnels

        # Open up a SSH tunnel to bastion_ip:22 through apl_bastion_ip
        # (to allow the second tunnel to be created)
        proc = create_tunnel(apl_bastion_key, port, bastion_ip, 22, apl_bastion_ip, apl_bastion_user)
        wrapper.prepend(proc)

        # Create our normal tunnel, but connect to localhost:port to use the
        # first tunnel that we create
        proc = create_tunnel(key, local_port, remote_ip, remote_port, "localhost", bastion_user, port)
        wrapper.prepend(proc)
        return wrapper

class ProcWrapper(list):
    """Wrapper that holds multiple Popen objects and can call
    terminate and wait on all contained objects.
    """
    def prepend(self, item):
        self.insert(0, item)
    def terminate(self):
        [item.terminate() for item in self]
    def wait(self):
        [item.wait() for item in self]

def locate_port():
    """Instead of trying to figure out if a port is in use, assume that it will
    not be in use.
    """
    return random.randint(10000,60000)

def become_tty_fg():
    """A helper function for subprocess.call(preexec_fn=) that makes the
    called command to become the foreground process in the terminal,
    allowing the user to interact with that process.

    Control is returned to this script after the called process has
    terminated.
    """
    #From: http://stackoverflow.com/questions/15200700/how-do-i-set-the-terminal-foreground-process-group-for-a-process-im-running-und

    os.setpgrp()
    hdlr = signal.signal(signal.SIGTTOU, signal.SIG_IGN)
    tty = os.open('/dev/tty', os.O_RDWR)
    os.tcsetpgrp(tty, os.getpgrp())
    signal.signal(signal.SIGTTOU, hdlr)

def ssh(key, remote_ip, bastion_ip):
    """Create an SSH tunnel from the local machine to bastion that gets
    forwarded to remote. Launch a second SSH connection (using
    become_tty_fg) through the SSH tunnel to the remote machine.

    After the second SSH session is complete, the SSH tunnel is destroyed.
    """
    ssh_port = locate_port()
    ssh_cmd = "ssh -i {} {} -p {} ubuntu@localhost".format(key, SSH_OPTIONS, ssh_port)

    proc = create_tunnel_aplnis(key, ssh_port, remote_ip, 22, bastion_ip)
    try:
        ret = subprocess.call(shlex.split(ssh_cmd), close_fds=True, preexec_fn=become_tty_fg)
    finally:
        proc.terminate()
        proc.wait()

def ssh_cmd(key, remote_ip, bastion_ip, command = None):
    """Create an SSH tunnel from the local machine to bastion that gets
    forwarded to remote. Launch a second SSH connection through the SSH tunnel
    to the remote machine.

    After the second SSH session is complete, the SSH tunnel is destroyed.
    """

    if command is None:
        command = input("command: ")

    ssh_port = locate_port()
    ssh_cmd_str = "ssh -i {} {} -p {} ubuntu@localhost '{}'".format(key, SSH_OPTIONS, ssh_port, command)

    proc = create_tunnel_aplnis(key, ssh_port, remote_ip, 22, bastion_ip)
    try:
        ret = subprocess.call(shlex.split(ssh_cmd_str))
    finally:
        proc.terminate()
        proc.wait()

def ssh_tunnel(key, remote_ip, bastion_ip, port = None, local_port = None, cmd = None):
    """Create an SSH tunnel from the local machine to bastion that gets
    forwarded to remote. Launch a second SSH tunnel through the SSH tunnel to
    the remote machine.

    After the second SSH session is complete, the SSH tunnel is destroyed.
    """
    if port is None:
        port = int(input("Target Port: "))

    if local_port is None:
        local_port = int(input("Local Port: ")) if cmd is None else locate_port()

    proc = create_tunnel_aplnis(key, local_port, remote_ip, port, bastion_ip)
    try:
        if cmd is None:
            print("Connect to localhost:{} to be forwarded to {}:{}".format(local_port, remote_ip, port))
            input("Waiting to close tunnel...")
        else:
            cmd(local_port)
    finally:
        proc.terminate()
        proc.wait()

def connect_vault(key, remote_ip, bastion_ip, cmd):
    """Create an SSH tunnel from the local machine to bastion that gets
    forwarded to remote. Call a command and then destroy the SSH tunnel.
    The SSH Tunnel forwards port 8200, the Vault default port.

    NOTE: Currently the commands that are passed to this function are
          defined in vault.py.
    """

    proc = create_tunnel_aplnis(key, 8200, remote_ip, 8200, bastion_ip)
    try:
        return cmd()
    finally:
        proc.terminate()
        proc.wait()

def create_session(cred_fh):
    """Read the AWS from the given JSON formated file and then create a boto3
    connection to AWS with those credentials.
    """
    credentials = json.load(cred_fh)

    session = Session(aws_access_key_id = credentials["aws_access_key"],
                      aws_secret_access_key = credentials["aws_secret_key"],
                      region_name = 'us-east-1')
    return session

def machine_lookup(session, hostname, public_ip = True):
    """Lookup the running EC2 instance with the name hostname. If a machine
    exists then return the public IP address (if it exists) or the private
    IP address (if it exists).
    """
    client = session.client('ec2')
    response = client.describe_instances(Filters=[{"Name":"tag:Name", "Values":[hostname]},
                                                  {"Name":"instance-state-name", "Values":["running"]}])

    item = response['Reservations']
    if len(item) == 0:
        return None
    else:
        item = item[0]['Instances']
        if len(item) == 0:
            return None
        else:
            item = item[0]
            if 'PublicIpAddress' in item and public_ip:
                return item['PublicIpAddress']
            elif 'PrivateIpAddress' in item:
                return item['PrivateIpAddress']
            else:
                return None

if __name__ == "__main__":
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    commands = ["ssh", "ssh-cmd", "ssh-tunnel"]
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
    parser.add_argument("--ssh-key", "-s",
                        metavar = "<file>",
                        default = os.environ.get("SSH_KEY"),
                        help = "SSH private key to use when connecting to AWS instances (default: SSH_KEY)")
    parser.add_argument("bastion", help="Hostname of the EC2 bastion server to create SSH Tunnels on")
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

    session = create_session(args.aws_credentials)
    bastion = machine_lookup(session, args.bastion)
    private = machine_lookup(session, args.internal, public_ip = False)

    if args.command in ("ssh",):
        ssh(args.ssh_key, private, bastion)
    elif args.command in ("ssh-cmd",):
        ssh_cmd(args.ssh_key, private, bastion, *args.arguments)
    elif args.command in ("ssh-tunnel",):
        ssh_tunnel(args.ssh_key, private, bastion, *args.arguments)
    elif args.command in vault.COMMANDS:
        connect_vault(args.ssh_key, private, bastion, lambda: vault.COMMANDS[args.command](args.internal, *args.arguments))
    else:
        parser.print_usage()
        sys.exit(1)
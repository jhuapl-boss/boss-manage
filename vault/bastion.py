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
    """Create a SSH tunnel.

    Creates a SSH tunnel from localhost:local_port to remote_ip:remote_port through bastion_ip.

    Args:
        key (string) : Path to a SSH private key, protected as required by SSH
        local_port : Port on the local machine to attach the local end of the tunnel to
        remote_ip : IP of the machine the tunnel remote end should point at
        remote_port : Port of on the remote_ip that the tunnel should point at
        bastion_ip : IP of the machine to form the SSH tunnel through
        bastion_user : The user account of the bastion_ip machine to use when creating the tunnel
        bastion_port : Port on the bastion_ip to connect to when creating the tunnel

    Returns:
        (Popen) : Popen process object of the SSH tunnel
    """
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
    """Create a SSH tunnel, possibly though an extra bastion defined by environmental variables.

    Read environmental variables to either directly connect to the given
    bastion_ip or use the given (second) bastion server as the first machine to
    connect to and route other tunnels through.

    This was added to support using a single machine given access through the
    corporate firewall and tunnel all SSH connections through it.

    Args:
        key (string) : Path to a SSH private key, protected as required by SSH
        local_port : Port on the local machine to attach the local end of the tunnel to
        remote_ip : IP of the machine the tunnel remote end should point at
        remote_port : Port of on the remote_ip that the tunnel should point at
        bastion_ip : IP of the machine to form the SSH tunnel through
        bastion_user : The user account of the bastion_ip machine to use when creating the tunnel

    Returns:
        (Popen) : Popen process object of the SSH tunnel
        (ProcWrapper) : ProcWrapper that contains multiple Popen objects, one for each tunnel
    """
    apl_bastion_ip = os.environ.get("BASTION_IP")
    apl_bastion_key = os.environ.get("BASTION_KEY")
    apl_bastion_user = os.environ.get("BASTION_USER")

    if apl_bastion_ip is None or apl_bastion_key is None or apl_bastion_user is None:
        # traffic
        # localhost -> bastion -> remote
        print("Bastion information not defined, connecting directly")
        return create_tunnel(key, local_port, remote_ip, remote_port, bastion_ip, bastion_user)
    else:
        # traffic
        # localhost -> apl_bastion -> bastion -> remote
        print("Using Bastion host at {}".format(apl_bastion_ip))
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
    """Locate a local port to attach a SSH tunnel to.

    Instead of trying to figure out if a port is in use, assume that it will
    not be in use.

    Returns:
        (int) : Local port to use
    """
    return random.randint(10000,60000)

def become_tty_fg():
    """Force a subprocess call to become the foreground process.

    A helper function for subprocess.call(preexec_fn=) that makes the
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
    """Create SSH tunnel(s) through bastion machine(s) and start a foreground
    SSH process.

    Create an SSH tunnel from the local machine to bastion that gets
    forwarded to remote. Launch a second SSH connection (using
    become_tty_fg) through the SSH tunnel to the remote machine.

    After the second SSH session is complete, the SSH tunnel is destroyed.

    Args:
        key (string) : Path to a SSH private key, protected as required by SSH
        remote_ip : IP of the machine the tunnel remote end should point at
        bastion_ip : IP of the machine to form the SSH tunnel through
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
    """Create SSH tunnel(s) through bastion machine(s) and execute a command over
    SSH.

    Create an SSH tunnel from the local machine to bastion that gets
    forwarded to remote. Launch a second SSH connection through the SSH tunnel
    to the remote machine and execute a command. After the command is complete
    the connections are closed.

    Args:
        key (string) : Path to a SSH private key, protected as required by SSH
        remote_ip : IP of the machine the tunnel remote end should point at
        bastion_ip : IP of the machine to form the SSH tunnel through
        command (None|string) : Command to execute on remote_ip. If command is
                                None, then prompt the user for the command to
                                execute.
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
    """Create SSH tunnel(s) through bastion machine(s) and setup a SSH tunnel.

        Note: This function will block until the user tells it to close the tunnel
              if cmd argument is None.

    Create an SSH tunnel from the local machine to bastion that gets
    forwarded to remote. Launch a second SSH tunnel through the SSH tunnel
    to the remote machine and wait for user input (or cmd to return) to close
    the tunnels.

    Args:
        key (string) : Path to a SSH private key, protected as required by SSH
        remote_ip : IP of the machine the tunnel remote end should point at
        bastion_ip : IP of the machine to form the SSH tunnel through
        port : Target port on remote_ip to form the SSH tunnel to
               If port is None then prompt the user for the port
        local_port : Local port to connect the SSH tunnel to
                     If local_port is None and cmd is None then the user is prompted
                         for the local port to use
                     If local_port is None and cmd is not None then a port is located
                         and passed to cmd
        cmd (None|function): If cmd is None, the tunnels are setup and the user
                             is prompted for when to close the tunnels else cmd
                             is called as a function, passing in local_port
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
    """Create SSH tunnel(s) through bastion machine(s) and call a command from
    vault.py.

    Create an SSH tunnel from the local machine to bastion that gets
    forwarded to remote. Call a command and then destroy the SSH tunnel.
    The SSH Tunnel forwards port 8200, the Vault default port.

    NOTE: Currently the commands that are passed to this function are
          defined in vault.py.

    Args:
        key (string) : Path to a SSH private key, protected as required by SSH
        remote_ip : IP of the machine the tunnel remote end should point at
        bastion_ip : IP of the machine to form the SSH tunnel through
        cmd (function): vault.py function expect to connect to Vault at localhost:8200
    """

    #proc = create_tunnel_aplnis(key, 8200, remote_ip, 8200, bastion_ip)
    # connection to bastion's http proxy server
    proc = create_tunnel_aplnis(key, 3128, "localhost", 3128, bastion_ip)
    try:
        return cmd()
    finally:
        proc.terminate()
        proc.wait()

def create_session(cred_fh):
    """Read AWS credentials from the given file object and create a Boto3 session.

        Note: Currently is hardcoded to connect to Region US-East-1

    Args:
        cred_fh (file) : File object of a JSON formated data with the following keys
                         "aws_access_key" and "aws_secret_key"

    Returns:
        (Session) : Boto3 session
    """
    credentials = json.load(cred_fh)

    session = Session(aws_access_key_id = credentials["aws_access_key"],
                      aws_secret_access_key = credentials["aws_secret_key"],
                      region_name = 'us-east-1')
    return session

def machine_lookup_all(session, hostname, public_ip = True):
    """Lookup all of the IP addresses for a given AWS instance name.

    Multiple instances with the same name is a result of instances belonging to
    an auto scale group. Useful when an action needs to happen to all machines
    in an auto scale group.

    Args:
        session (Session) : Active Boto3 session
        hostname (string) : Hostname of the EC2 instances
        public_ip (bool) : Whether or not to return public IPs or private IPs

    Returns:
        (list) : List of IP addresses
    """
    client = session.client('ec2')
    response = client.describe_instances(Filters=[{"Name":"tag:Name", "Values":[hostname]},
                                                  {"Name":"instance-state-name", "Values":["running"]}])

    addresses = []
    items = response['Reservations']
    if len(items) > 0:
        for i in items:
            item = i['Instances'][0]
            if 'PublicIpAddress' in item and public_ip:
                addresses.append(item['PublicIpAddress'])
            elif 'PrivateIpAddress' in item and not public_ip:
                addresses.append(item['PrivateIpAddress'])
    return addresses

def machine_lookup(session, hostname, public_ip = True):
    """Lookup the IP addresses for a given AWS instance name.

        Note: If not address could be located an error message is printed

    If there are multiple machines with the same hostname, to select a specific
    one, prepend the hostname with "#." where '#' is the zero based index.
        Example: 0.auth.integration.boss

    Retrieved instances are sorted by InstanceId.

    Args:
        session (Session) : Active Boto3 session
        hostname (string) : Hostname of the EC2 instance
        public_ip (bool) : Whether or not to return the public IP or private IP

    Returns:
        (string|None) : IP address or None if one could not be located.
    """

    try:
        idx, target = hostname.split('.', 1)
        idx = int(idx) # if it is not a valid number, then it is a hostname
        hostname = target
    except:
        idx = 0

    client = session.client('ec2')
    response = client.describe_instances(Filters=[{"Name":"tag:Name", "Values":[hostname]},
                                                  {"Name":"instance-state-name", "Values":["running"]}])

    item = response['Reservations']
    if len(item) == 0:
        print("Could not find IP address for '{}'".format(hostname))
        return None
    else:
        item.sort(key = lambda i: i['Instances'][0]["InstanceId"])

        if len(item) <= idx:
            print("Could not find IP address for '{}' index '{}'".format(hostname, idx))
            return None
        else:
            item = item[idx]['Instances'][0]
            if 'PublicIpAddress' in item and public_ip:
                return item['PublicIpAddress']
            elif 'PrivateIpAddress' in item and not public_ip:
                return item['PrivateIpAddress']
            else:
                print("Could not find IP address for '{}'".format(hostname))
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
    parser.add_argument("--private-ip", "-p",
                        action='store_true',
                        default=False,
                        help = "add this flag to type in a private IP address in internal command instead of a DNS name which is looked up")
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
    if args.private_ip:
        private = args.internal
    else:
        private = machine_lookup(session, args.internal, public_ip=False)

    if args.command in ("ssh",):
        ssh(args.ssh_key, private, bastion)
    elif args.command in ("ssh-cmd",):
        ssh_cmd(args.ssh_key, private, bastion, *args.arguments)
    elif args.command in ("ssh-tunnel",):
        ssh_tunnel(args.ssh_key, private, bastion, *args.arguments)
    elif args.command in vault.COMMANDS:
        connect_vault(args.ssh_key, private, bastion, lambda: vault.COMMANDS[args.command](args.internal, private, *args.arguments))
    else:
        parser.print_usage()
        sys.exit(1)

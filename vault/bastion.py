#!/usr/bin/env python3

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
from boto3.session import Session
import json
import vault

# Needed to prevent ssh from asking about the fingerprint from new machines
SSH_OPTIONS = "-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no"

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

def ssh(key, remote, bastion):
    """Create an SSH tunnel from the local machine to bastion that gets
    forwarded to remote. Launch a second SSH connection (using
    become_tty_fg) through the SSH tunnel to the remote machine.
    
    After the second SSH session is complete, the SSH tunnel is destroyed.
    
    NOTE: This command uses fixed port numbers, so only one instance of this
          command can be launched on a single machine at the same time.
    """
    fwd_cmd = "ssh -i {} {} -N -L 2222:{}:22 ec2-user@{}".format(key, SSH_OPTIONS, remote, bastion)
    ssh_cmd = "ssh -i {} {} -p 2222 ubuntu@localhost".format(key, SSH_OPTIONS)
    
    proc = subprocess.Popen(shlex.split(fwd_cmd))
    time.sleep(1) # wait for the tunnel to be setup
    try:
        ret = subprocess.call(shlex.split(ssh_cmd), close_fds=True, preexec_fn=become_tty_fg)
    finally:
        proc.terminate()
        proc.wait()
    
def connect_vault(key, remote, bastion, cmd):
    """Create an SSH tunnel from the local machine to bastion that gets
    forwarded to remote. Call a command and then destroy the SSH tunnel.
    The SSH Tunnel forwards port 8200, the Vault default port.
    
    NOTE: Currently the commands that are passed to this function are
          defined in vault.py.
    """
    fwd_cmd = "ssh -i {} {} -N -L 8200:{}:8200 ec2-user@{}".format(key, SSH_OPTIONS, remote, bastion)

    proc = subprocess.Popen(shlex.split(fwd_cmd))
    time.sleep(1) # wait for the tunnel to be setup
    try:
        cmd()
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
    
def machine_lookup(session, hostname):
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
            if 'PublicIpAddress' in item:
                return item['PublicIpAddress']
            elif 'PrivateIpAddress' in item:
                return item['PrivateIpAddress']
            else:
                return None

if __name__ == "__main__":
    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    commands = ["ssh"]
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

    args = parser.parse_args()
    
    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)
    if args.ssh_key is None:
        parser.print_usage()
        print("Error: SSH key not provided and SSH_KEY is not defined")
        sys.exit(1)
    # Add check to make sure ssh_key exists

    session = create_session(args.aws_credentials)
    bastion = machine_lookup(session, args.bastion)
    private = machine_lookup(session, args.internal)
    
    if args.command in ("ssh",):
        ssh(args.ssh_key, private, bastion)
    elif args.command in vault.COMMANDS:
        connect_vault(args.ssh_key, private, bastion, vault.COMMANDS[args.command])
    else:
        parser.print_usage()
        sys.exit(1)
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

def ssh(key, ip, user="ubuntu"):
    """Create an SSH tunnel from the local machine to bastion that gets
    forwarded to remote. Launch a second SSH connection (using
    become_tty_fg) through the SSH tunnel to the remote machine.
    
    After the second SSH session is complete, the SSH tunnel is destroyed.
    
    NOTE: This command uses fixed port numbers, so only one instance of this
          command can be launched on a single machine at the same time.
    """
    ssh_cmd = "ssh -i {} {} {}@{}".format(key, SSH_OPTIONS, user, ip)
    
    subprocess.call(shlex.split(ssh_cmd), close_fds=True, preexec_fn=become_tty_fg)

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
            else:
                return None

if __name__ == "__main__":
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
    parser.add_argument("hostname", help="Hostname of the EC2 instance to create SSH Tunnels on")

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
    ip = machine_lookup(session, args.hostname)
    
    ssh(args.ssh_key, ip)
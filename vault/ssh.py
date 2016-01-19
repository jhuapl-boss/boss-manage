#!/usr/bin/env python3

"""A script for looking up the IP address of an AWS instance and then starting
an SSH session with the machine.

SSH_OPTIONS - Extra command line options that are passed to every SSH call
"""

import argparse
import subprocess
import shlex
import os
import sys

from bastion import *


def tunnel_aplnis(ip):
    apl_bastion_ip = os.environ.get("BASTION_IP")
    apl_bastion_key = os.environ.get("BASTION_KEY")
    apl_bastion_user = os.environ.get("BASTION_USER")
    
    if apl_bastion_ip is None or apl_bastion_key is None or apl_bastion_user is None:
        print("APL Bastion information not defined, connecting directly")
        return (None, None)
    else:
        print("Using APL Bastion host at {}".format(apl_bastion_ip))
        port = locate_port()
        proc = create_tunnel(apl_bastion_key, port, ip, 22, apl_bastion_ip, apl_bastion_user)
        return (proc, port)

def ssh(key, ip, user="ubuntu"):
    """Create an SSH session from the local machine to the given remote
    remote IP address (using become_tty_fg).
    """
    
    proc, port = tunnel_aplnis(ip)
    if port is None:
        port = 22
    else:
        ip = "localhost"
    
    try:
        ssh_cmd = "ssh -i {} {} -p {} {}@{}".format(key, SSH_OPTIONS, port, user, ip)
        subprocess.call(shlex.split(ssh_cmd), close_fds=True, preexec_fn=become_tty_fg)
    finally:
        if proc is not None:
            proc.terminate()
            proc.wait()


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
    user = "ec2-user" if args.hostname.startswith("bastion") else "ubuntu"
    
    ssh(args.ssh_key, ip, user)

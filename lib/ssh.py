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

import subprocess
import shlex
import os
import signal
import sys
import time
import random

from contextlib import contextmanager

from .exceptions import SSHError, SSHTunnelError

# Needed to prevent ssh from asking about the fingerprint from new machines
SSH_OPTIONS = "-o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -q"
TUNNEL_SLEEP = 10 # seconds

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

def check_ssh(ret):
    if ret == 255:
        raise SSHError("Error establishing a SSH connection")

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

    try:
        r = proc.wait(TUNNEL_SLEEP)
        if r == 255:
            raise SSHError("Error establishing a SSH tunnel")
        else:
            raise SSHTunnelError("SSH tunnel exited with error code {}".format(ret))
    except subprocess.TimeoutExpired:
        pass # process is still running, tunnel is up

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
        proc = create_tunnel(key, local_port, remote_ip, remote_port, bastion_ip, bastion_user)
        return proc
    else:
        # traffic
        # localhost -> apl_bastion -> bastion -> remote
        #print("Using Bastion host at {}".format(apl_bastion_ip))
        wrapper = ProcWrapper()
        port = locate_port()

        # Used http://superuser.com/questions/96489/ssh-tunnel-via-multiple-hops mssh.pl
        # to figure out the multiple tunnels

        # Open up a SSH tunnel to bastion_ip:22 through apl_bastion_ip
        # (to allow the second tunnel to be created)
        proc = create_tunnel(apl_bastion_key, port, bastion_ip, 22, apl_bastion_ip, apl_bastion_user)
        wrapper.prepend(proc)

        try:
            # Create our normal tunnel, but connect to localhost:port to use the
            # first tunnel that we create
            proc = create_tunnel(key, local_port, remote_ip, remote_port, "localhost", bastion_user, port)
            wrapper.prepend(proc)
            return wrapper
        except:
            # close the initial tunnel
            wrapper.terminate()
            wrapper.wait()
            raise # raise initial exception

def unpack(obj, *args):
    if type(obj) == tuple:
        args_ = list(args)[len(obj)-1:]
        return (*obj, *args_)
    else:
        return (obj, *args)

class SSHConnection(object):
    def __init__(self, key, target, bastion, local_port=None):
        self.key = key
        self.remote_ip, self.remote_port, self.remote_user = unpack(target, 22, "ubuntu")
        self.bastion_ip, self.bastion_port, self.bastion_user = unpack(bastion, 22, "ec2-user")
        self.local_port = local_port if local_port else random.randint(10000,60000)

    @contextmanager
    def _connect(self):
        proc = create_tunnel_aplnis(self.key,
                                    self.local_port, 
                                    self.remote_ip,
                                    self.remote_port, 
                                    self.bastion_ip, 
                                    self.bastion_user)
        try:
            yield
        finally:
            proc.terminate()
            proc.wait()

    def shell(self):
        """Create SSH tunnel(s) through bastion machine(s) and start a foreground
        SSH process.

        Create an SSH tunnel from the local machine to bastion that gets
        forwarded to remote. Launch a second SSH connection (using
        become_tty_fg) through the SSH tunnel to the remote machine.

        After the second SSH session is complete, the SSH tunnel is destroyed.
        """
        ssh_cmd = "ssh -i {} {} -p {} {}@localhost" \
                        .format(self.key, SSH_OPTIONS, self.local_port, self.remote_user)

        with self._connect():
            ret = subprocess.call(shlex.split(ssh_cmd), close_fds=True, preexec_fn=become_tty_fg)
            check_ssh(ret)
            return ret

    @contextmanager
    def cmds(self):
        """Create SSH tunnel(s) through bastion machine(s) and return a function
        that will execute commands over SSH.

        Create an SSH tunnel from the local machine to bastion that gets
        forwarded to remote. Launch a second SSH connection through the SSH tunnel
        to the remote machine and execute a command. After the command is complete
        the connections are closed.

        with SSHConnection().cmds as cmd:
            cmd("command to execute")
            cmd("command to execute")
        """
        def cmd(command):
            ssh_cmd_str = "ssh -i {} {} -p {} {}@localhost '{}'" \
                                .format(self.key, SSH_OPTIONS, self.local_port, self.remote_user, command)

            ret = subprocess.call(shlex.split(ssh_cmd_str))
            check_ssh(ret)
            return ret

        with self._connect():
            yield cmd

    def cmd(self, command = None):
        """Create SSH tunnel(s) through bastion machine(s) and execute a command over
        SSH.

        Create an SSH tunnel from the local machine to bastion that gets
        forwarded to remote. Launch a second SSH connection through the SSH tunnel
        to the remote machine and execute a command. After the command is complete
        the connections are closed.

        Args:
            command (None|string) : Command to execute on remote_ip. If command is
                                    None, then prompt the user for the command to
                                    execute.
        """

        if command is None:
            command = input("command: ")

        with self.cmds() as cmd:
            cmd(command)

    @contextmanager
    def tunnel(self):
        """Create SSH tunnel(s) through bastion machine(s), setup a SSH tunnel,
        and return the local port to connect to.
        """
        with self._connect():
            yield self.local_port

    def external_tunnel(self, port = None, local_port = None):
        """Create SSH tunnel(s) through bastion machine(s) and setup a SSH tunnel.

            Note: This function will block until the user tells it to close the tunnel
                  if cmd argument is None.

        Create an SSH tunnel from the local machine to bastion that gets
        forwarded to remote. Launch a second SSH tunnel through the SSH tunnel
        to the remote machine and wait for user input to close the tunnels.

        Args:
            port : Target port on remote_ip to form the SSH tunnel to
                   If port is None then prompt the user for the port
            local_port : Local port to connect the SSH tunnel to
                         If local_port is None and cmd is None then the user is prompted
                             for the local port to use
                         If local_port is None and cmd is not None then a port is located
                             and passed to cmd
        """
        if port is None:
            port = int(input("Target Port: "))
        self.remote_port = port

        if local_port is None:
            local_port = int(input("Local Port: "))
        self.local_port = local_port

        with self._connect():
            print("Connect to localhost:{} to be forwarded to {}:{}"
                        .format(self.local_port, self.remote_ip, self.remote_port))
            input("Waiting to close tunnel...")

def vault_tunnel(key, bastion):
    ssh = SSHConnection(key, ("localhost", 3128), bastion, local_port=3128)
    return ssh.tunnel()

class ConnectionManager(object):
    def __init__(self, key, remote, bastion, local_port=None):
        self.base = SSHConnection(key, remote, bastion, local_port)
        self.connections = {}


    def get(self, target):
        if target not in self.connections:
            target_ = unpack(target, self.base.remote_port, self.base.remote_user)
            self.connections[target] = SSHConnection(self.base.key,
                                                     target_,
                                                     (self.base.bastion_ip, self.base.bastion_port, self.base.bastion_user),
                                                     self.base.local_port)
        return self.connections[target]




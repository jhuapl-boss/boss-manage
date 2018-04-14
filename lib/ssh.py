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

def unpack(obj, *args):
    if type(obj) == tuple:
        args_ = list(args)[len(obj)-1:]
        return (*obj, *args_)
    else:
        return (obj, *args)

class SSHTarget(object):
    def __init__(self, key, ip, port='22', user='ec2-user'):
        self.key = key
        self.ip = ip
        self.port = port
        self.user = user

    def __str__(self):
        return "{}@{}:{}".format(self.user, self.ip, self.port)

class SSHConnection(object):
    def __init__(self, target, bastions=[], local_port=None):
        if isinstance(bastions, SSHTarget): # easy passing of a single bastion
            bastions = [bastions]

        self.target = target
        self.bastions = bastions
        self.local_port = local_port if local_port else locate_port()

    @contextmanager
    def _connect(self):
        """Create the needed SSH tunnel(s) based on constructor arguments.

        There are 4 different tunnel configurations
        1) No tunnels are needed / requested
        2) One tunnel though the bastion defined by environment variables
        3) One tunnel though the bastion passed to the constructor
        4) Two tunnels one through the bastion defined by environment variables
           and on throught he bastion passed to the constructor

        Returns:
            (hostname/ip, port) : Tuple of hostname/ip and port to connect to
                                  Needed so the calling method(s) know if they
                                  connect to localhost or remote_ip (depending
                                  on if a tunnel(s) was created
        """
        wrapper = ProcWrapper()
        # create_tunnel(key, l_port, r_ip, r_port, b_ip, b_user, b_port)
        # ssh -L l_port:r_ip:r_port -p b_port p_user@b_ip
        # connect l_port to r_ip:r_port via p_user@b_ip:b_port

        """
        b[1].l_port - (b[0].user@b[0].ip:b[0].port) -> b[1].ip:b[1].port
        b[n].l_port - (b[1].user@localhost:b[1].l_port) -> b[n].ip:b[n].port

        l_port - (b[n].user@localhost:b[n].l_port) -> r_ip:r_port


        b[-1].l_port, b[-1].ip, b[-1].port, b[-2].ip, b[-2].user, b[-2].l_port
        l_port, remote.ip, remote.port, "localhost", b[-1].user, b[-1].l_port
        """

        if len(self.bastions) == 0:
            print("No bastions defined, connecting directly")
            args = self.remote
        else:
            # Connecting from local_port to remote via bastion
            # all three lists will be the same length
            local_ports = []
            bastions = [(self.bastions[0].key,
                         self.bastions[0].user,
                         self.bastions[0].ip,
                         self.bastions[0].port)]
            remotes = []  # ip, port

            for bastion in self.bastions[1:]:
                port = locate_port()
                local_ports.append(port)
                bastions.append((bastion.key, bastion.user, "localhost", port))
                remotes.append((bastion.ip, bastion.port))

            local_ports.append(self.local_port)
            remotes.append((self.target.ip, self.target.port))

            # Information for the caller to use when forming the final connection
            # through the established tunnels
            args = SSHTarget(self.target.key,
                             "localhost",
                             self.local_port,
                             self.target.user)

            wrapper = ProcWrapper()
            for i in range(len(bastions)):
                l_port = local_ports[i]
                b = bastions[i]
                r = remotes[i]
                #print("Connecting {} -> ({}@{}:{}) -> {}:{}".format(l_port,
                #                                                    b[1], # b.user
                #                                                    b[2], # b.ip
                #                                                    b[3], # b.port
                #                                                    r[0], # r.ip
                #                                                    r[1])) # r.port

                try:
                    proc = create_tunnel(b[0], # b.key
                                         l_port,
                                         r[0], # r.ip
                                         r[1], # r.port
                                         b[2], # b.ip
                                         b[1], # b.user
                                         b[3]) # b.port

                    wrapper.prepend(proc)
                except:
                    # close the tunnels that have been already created
                    wrapper.terminate()
                    wrapper.wait()
                    raise # raise initial exception

        try:
            yield args
        finally:
            if wrapper:
                wrapper.terminate()
                wrapper.wait()

    def shell(self):
        """Create SSH tunnel(s) through bastion machine(s) and start a foreground
        SSH process.

        Create an SSH tunnel from the local machine to bastion that gets
        forwarded to remote. Launch a second SSH connection (using
        become_tty_fg) through the SSH tunnel to the remote machine.

        After the second SSH session is complete, the SSH tunnel is destroyed.
        """

        with self._connect() as target:
            ssh_cmd = "ssh -i {} {} -p {} {}@{}" \
                            .format(target.key, SSH_OPTIONS, target.port, target.user, target.ip)

            ret = subprocess.call(shlex.split(ssh_cmd), close_fds=True, preexec_fn=become_tty_fg)
            check_ssh(ret)
            return ret

    # DP TODO: combind scps and cmds together to a user can scp and ssh over the same tunnel
    @contextmanager
    def scps(self):
        """Create SSH tunnel(s) through bastion machine(s) and return a function
        that will copy files over SSH.

        with SSHConnection().scps() as scp:
            scp(local_file, remote_file, upload=False)
            scp(local_file, remote_file, upload=True)
        """
        with self._connect() as target:
            def scp(local_file, remote_file, upload=False):
                first = local_file if upload else ""
                second = "" if upload else local_file
                scp_str = "scp -i {} {} -P {} {} {}@{}:{} {}" \
                                .format(target.key, SSH_OPTIONS, taret.port, first, target.user, target.ip, remote_file, second)
                ret = subprocess.call(shlex.split(scp_str))
                check_ssh(ret)
                return ret

            yield scp

    def scp(self, local_file=None, remote_file=None, upload=None):
        """Create SSH tunnel(s) through bastion machine(s) and execute a file copy over
        SSH.

        Args:
            local_file (None|String) : Local file path to upload from or download to.
                                       If None, then prompt the user for the file path
            remote_file (None|String) : Remote file path to upload from or download to.
                                        If None, then prompt the user for the file path
            upload (None:Bool): If the local file is being uploaded to the remote file
                                or it is being downloaded.
                                If None, then prompt the user for if this is an upload or download
        """
        if local_file is None:
            local_file = input("local file: ")

        if remote_file is None:
            remote_file = input("remote file: ")

        def parse_upload(s):
            if type(s) == bool:
                return s

            if s and len(s) > 0:
                if s[0] in ('U', 'u'):
                    return True
                elif s[0] in ('D', 'd'):
                    return False
            return None

        upload_ = None
        if upload is not None:
            upload_ = parse_upload(upload)
            if upload_ is None:
                print("'{}' is not upload or download".format(upload))

        if upload_ is None:
            upload_ = parse_upload(input("[u]pload / [D]ownload: ").strip())

        with self.scps() as cmd:
            return cmd(local_file, remote_file, upload)

    @contextmanager
    def cmds(self):
        """Create SSH tunnel(s) through bastion machine(s) and return a function
        that will execute commands over SSH.

        Create an SSH tunnel from the local machine to bastion that gets
        forwarded to remote. Launch a second SSH connection through the SSH tunnel
        to the remote machine and execute a command. After the command is complete
        the connections are closed.

        with SSHConnection().cmds() as cmd:
            cmd("command to execute")
            cmd("command to execute")
        """
        with self._connect() as target:
            def cmd(command):
                ssh_cmd_str = "ssh -i {} {} -p {} {}@{} '{}'" \
                                    .format(target.key, SSH_OPTIONS, target.port, target.user, target.ip, command)

                ret = subprocess.call(shlex.split(ssh_cmd_str))
                check_ssh(ret)
                return ret

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
            return cmd(command)

    @contextmanager
    def tunnel(self):
        """Create SSH tunnel(s) through bastion machine(s), setup a SSH tunnel,
        and return the local port to connect to.
        """
        if len(self.bastions) == 0:
            raise Exception("Cannot tunnel without bastion machine(s)")

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
        if len(self.bastions) == 0:
            print("No bastion(s) defined, connect directly to {}:{}".format(self.target.ip, self.target.port))
            return

        if port is None:
            port = int(input("Target Port: "))
        self.target.port = port

        if local_port is None:
            local_port = int(input("Local Port: "))
        self.local_port = local_port

        with self._connect():
            print("Connect to localhost:{} to be forwarded to {}:{}"
                        .format(self.local_port, self.target.ip, self.target.port))
            input("Waiting to close tunnel...")

def vault_tunnel(key, bastions):
    ssh = SSHConnection(SSHTarget(key, 'localhost', 3128, 'ubuntu'),
                        bastions, local_port=3128)
    return ssh.tunnel()


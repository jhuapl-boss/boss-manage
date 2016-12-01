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

import time
from urllib.request import urlopen

import exceptions
import bastion
import vault
from xxx import keypair_to_file

def gen_timeout(total, step):
    """Break the total timeout value into steps
    that are a specific size.

    Args:
        total (int) : total number seconds
        step (int) : length of step

    Returns:
        (list) : list containing a repeated number of step
                 plus the remainder if step doesn't evenly divide
    """
    times, remainder = divmod(total, step)
    rtn = [step for i in range(times)]
    if remainder > 0:
        rtn.insert(0, remainder) # Sleep for the partial time first
    return rtn

class ExternalCalls:
    """Class that helps with forming connections from the local machine to machines
    within a VPC through the VPC's bastion machine.
    """
    def __init__(self, session, keypair, domain):
        """ExternalCalls constructor

        Args:
            session (Session) : Boto3 session used to lookup machine IPs in AWS
            keypair (string) : Name of the AWS EC2 keypair to use when connecting
                               All AWS EC2 instances connected to need to use the
                               same keypair
                               Keypair is converted to file on disk using keypair_to_file()
            domain (string) : BOSS internal VPC domain name
        """
        self.session = session
        self.keypair_file = keypair_to_file(keypair)
        self.bastion_hostname = "bastion." + domain
        self.bastion_ip = bastion.machine_lookup(session, self.bastion_hostname)
        self.vault_hostname = "vault." + domain
        self.vault_ip = bastion.machine_lookup(session, self.vault_hostname, public_ip=False)
        self.domain = domain
        self.ssh_target = None

    def vault_check(self, timeout, exception=True):
        """Vault status check to see if Vault is accessible
        """
        def delegate():
            for sleep in gen_timeout(timeout, 15): # 15 second sleep
                if vault.vault_status_check(machine=self.vault_hostname, ip=self.vault_ip):
                    return True
                time.sleep(sleep)

            if exception:
                msg = "Cannot connect to Vault after {} seconds".format(timeout)
                raise exceptions.StatusCheckError(msg, self.vault_hostname)
            else:
                return False

        return bastion.connect_vault(self.keypair_file, self.vault_ip, self.bastion_ip, delegate)

    def vault_init(self):
        """Initialize and configure all of the vault servers.

        Lookup all vault IPs for the VPC, initialize and configure the first server
        and then unseal any other servers.
        """
        vaults = bastion.machine_lookup_all(self.session, self.vault_hostname, public_ip=False)

        def connect(ip, func):
            bastion.connect_vault(self.keypair_file, ip, self.bastion_ip, func)

        connect(vaults[0], lambda: vault.vault_init(machine=self.vault_hostname, ip=vaults[0]))
        for ip in vaults[1:]:
            connect(ip, lambda: vault.vault_unseal(machine=self.vault_hostname, ip=ip))

    def vault_unseal(self):
        """Unseal all of the vault servers.

        Lookup all vault IPs for the VPC and unseal each server.
        """
        vaults = bastion.machine_lookup_all(self.session, self.vault_hostname, public_ip=False)

        def connect(ip, func):
            bastion.connect_vault(self.keypair_file, ip, self.bastion_ip, func)

        for ip in vaults:
            connect(ip, lambda: vault.vault_unseal(machine=self.vault_hostname, ip=ip))

    def vault(self, cmd, *args, **kwargs):
        """Call the specified vault command (from vault.py) with the given arguments

        Args:
            cmd (string) : Name of the vault command to execute (name of function
                           defined in vault.py)
            args (list) : Positional arguments to pass to the vault command
            kwargs (dict) : Keyword arguments to pass to the vault command

        Returns:
            (object) : Value returned by the vault command
        """
        def delegate():
            # Have to dynamically lookup the function because vault.COMMANDS
            # references the command line version of the commands we want to execute
            return vault.__dict__[cmd.replace('-', '_')](*args, machine=self.vault_hostname, ip=self.vault_ip, **kwargs)

        return bastion.connect_vault(self.keypair_file, self.vault_ip, self.bastion_ip, delegate)

    def vault_write(self, path, **kwargs):
        """Vault vault-write with the given arguments

        WARNING: vault-write will override any data at the given path

        Args:
            path (string) : Vault path to write data to
            kwargs (dict) : Keyword key value pairs to store in Vault
        """
        self.vault("vault-write", path, **kwargs)

    def vault_update(self, path, **kwargs):
        """Vault vault-update with the given arguments

        Args:
            path (string) : Vault path to write data to
            kwargs (dict) : Keyword key value pairs to store in Vault
        """
        self.vault("vault-update", path, **kwargs)

    def vault_read(self, path):
        """Vault vault-read for the given path

        Args:
            path (string) : Vault path to read data from

        Returns:
            (None|dict) : None if no data or dictionary of key value pairs stored
                          at Vault path
        """
        res = self.vault("vault-read", path)
        return None if res is None else res['data']

    def vault_delete(self, path):
        """Vault vault-delete for the givne path

        Args:
            path (string) : Vault path to delete data from
        """
        self.vault("vault-delete", path)

    def set_ssh_target(self, target):
        """Set the target machine for the SSH commands

        Args:
            target (string) : target machine name. If the name is not fully qualified
                              it is qualified using the domain given in the constructor.
        """
        self.ssh_target = target
        if not target.endswith("." + self.domain):
            self.ssh_target += "." + self.domain
        self.ssh_target_ip = bastion.machine_lookup(self.session, self.ssh_target, public_ip=False)

    def ssh(self, cmd):
        """Execute a command over SSH on the SSH target

        Args:
            cmd (string) : Command to execute on the SSH target

        Returns:
            (None)
        """
        if self.ssh_target is None:
            raise Exception("No SSH Target Set")

        return bastion.ssh_cmd(self.keypair_file,
                               self.ssh_target_ip,
                               self.bastion_ip,
                               cmd)

    def ssh_tunnel(self, cmd, port, local_port=None):
        """Execute a function within a SSH tunnel.

        Args:
            cmd (string) : Function to execute after the tunnel is established
                           Function is passed the local port of the tunnel to use
            port (int|string) : Remote port to use for tunnel
            local_port (None|int|string : Local port to use for tunnel or None if
                                          the function should select a random port

        Returns:
            None
        """
        if self.ssh_target is None:
            raise Exception("No SSH Target Set")

        return bastion.ssh_tunnel(self.keypair_file,
                                  self.ssh_target_ip,
                                  self.bastion_ip,
                                  port,
                                  local_port,
                                  cmd)

    def ssh_all(self, hostname, cmd):
        machines = bastion.machine_lookup_all(self.session, hostname, public_ip=False)

        for ip in machines:
            bastion.ssh_cmd(self.keypair_file,
                            ip,
                            self.bastion_ip,
                            cmd)

    def keycloak_check(self, timeout, exception=True):
        """Keycloak status check to see if Keycloak is accessible
        """
        # DP ???: use the actual login url so the actual API is checked..
        #         (and parse response for 403 unauthorized vs any other error..)

        def delegate(port):
            # Could move to connecting through the ELB, but then KC will have to be healthy
            URL = "http://localhost:{}/auth/".format(port)

            for sleep in gen_timeout(timeout, 15): # 15 second sleep
                try:
                    res = urlopen(URL)
                    if res.getcode() == 200:
                        return True
                except HTTPError:
                    pass
                time.sleep(sleep)

            if exception:
                msg = "Cannot connect to Keycloak after {} seconds".format(timeout)
                raise exceptions.StatusCheckError(msg, self.ssh_target)
            else:
                return False

        # DP TODO: save and restore previous ssh_target
        self.set_ssh_target("auth")
        return self.ssh_tunnel(delegate, 8080)

    def http_check(self, url, timeout, exception=True):
        for sleep in gen_timeout(timeout, 15): # 15 second sleep
            res = urlopen(url)
            if res.getcode() == 200:
                return True
            time.sleep(sleep)

        if exception:
            msg = "Cannot connect to URL after {} seconds".format(timeout)
            raise exceptions.StatusCheckError(msg, url)
        else:
            return False

    def django_check(self, machine, manage_py, exception=True):
        self.set_ssh_target(machine)
        cmd = "sudo python3 {} check 2> /dev/null > /dev/null".format(manage_py) # suppress all output

        ret = self.ssh(cmd)
        if exception and ret != 0:
            msg = "Problem with the endpoint's Django configuration"
            raise exceptions.StatusCheckError(msg, self.ssh_target)

        return ret == 0 # 0 - no issues, 1 - problems


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
import logging

from urllib.request import urlopen, HTTPError
from contextlib import contextmanager
from mysql import connector
from . import exceptions
from . import aws
from .utils import keypair_to_file
from .ssh import SSHConnection, SSHTarget, vault_tunnel
from .vault import Vault
from .exceptions import SSHError
from .names import AWSNames

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
    def __init__(self, bosslet_config):
        """ExternalCalls constructor

        Args:
            session (Session) : Boto3 session used to lookup machine IPs in AWS
            keypair (string) : Name of the AWS EC2 keypair to use when connecting
                               All AWS EC2 instances connected to need to use the
                               same keypair
                               Keypair is converted to file on disk using keypair_to_file()
            domain (string) : BOSS internal VPC domain name
        """
        self.names = bosslet_config.names
        self.session = bosslet_config.session
        self.keypair_file = bosslet_config.ssh_key

        bastion_ip = aws.machine_lookup(self.session, self.names.bastion.dns)

        self.bastions = [ SSHTarget(self.keypair_file, bastion_ip) ]

        if bosslet_config.outbound_bastion:
            self.bastions.insert(0, bosslet_config.outbound_bastion)

        self.vault_hostname = self.names.vault.dns
        ips = aws.machine_lookup_all(self.session,
                                     self.vault_hostname,
                                     public_ip=False)
        self.vaults = [Vault(self.vault_hostname, ip) for ip in ips]

        # keep track of previous connections to limit the need for looking up IP addresses
        self.connections = {}

    @contextmanager
    def vault(self):
        class ContextVault(object):
            @staticmethod
            def initialize(account_id):
                """Initialize and configure all of the vault servers.

                Lookup all vault IPs for the VPC, initialize and configure the first server
                and then unseal any other servers.
                """
                self.vaults[0].initialize(account_id)
                for vault in self.vaults[1:]:
                    vault.unseal()

            @staticmethod
            def unseal():
                """Unseal all of the vault servers.

                Lookup all vault IPs for the VPC and unseal each server.
                """
                for vault in self.vaults:
                    vault.unseal()

            @staticmethod
            def read(path):
                """Read data from vault and return just the dict of data"""
                data = self.vaults[0].read(path)
                return data['data'] if data else None

            @staticmethod
            def export(path):
                """Export data from vault and return just the dict of data"""
                data = self.vaults[0].export(path)
                return data if data else None
            
            @staticmethod
            def import_(path):
                """Import data from vault and return just the dict of data"""
                data = self.vaults[0].import_(path)
                return data if data else None

            # DP NOTE: Bind basic methods to the Vault object methods
            write = self.vaults[0].write
            update = self.vaults[0].update
            delete = self.vaults[0].delete
            provision = self.vaults[0].provision
            revoke = self.vaults[0].revoke
            revoke_secret_prefix = self.vaults[0].revoke_secret_prefix
            set_policy = self.vaults[0].set_policy
            list_policies = self.vaults[0].list_policies

        with vault_tunnel(self.keypair_file, self.bastions):
            yield ContextVault()

    def ssh(self, target):
        """Open a SSH connection to the target machine (AWS instance name) and return a method
        that can be used to execute commands on the remote machines.
        """
        # DP ???: Should cf_config be passed so we can lookup the full hostname
        #         and use the correct session object
        if target not in self.connections:
            target_ip = aws.machine_lookup(self.session, target, public_ip=False)

            ssh_target = SSHTarget(self.keypair_file, target_ip, 22, 'ubuntu')
            self.connections[target] = SSHConnection(ssh_target, self.bastions)

        return self.connections[target].cmds()

    def tunnel(self, target, port, type_='ec2'):
        """Open a SSH connectio to the target machine (AWS instance name) / port and return the local
        port of the tunnel to connect to.
        """
        # DP ???: Should cf_config be passed so we can lookup the full hostname
        #         and use the correct session object
        key = (target, port)
        if key not in self.connections:
            if type_ == 'ec2':
                target_ip = aws.machine_lookup(self.session, target, public_ip=False)
            elif type_ == 'rds':
                target_ip = aws.rds_lookup(self.session, target.replace('.', '-'))
            else:
                raise Exception("Unsupported: tunnelling to machine type {}".format(type_))
            ssh_target = SSHTarget(self.keypair_file, target_ip, port, 'ubuntu')
            self.connections[key] = SSHConnection(ssh_target, self.bastions)

        return self.connections[key].tunnel()

    @contextmanager
    def connect_rds(self, return_connection=False):
        """
        Context manager with established connection to endpoint boss rds. Connection can be returned to allow updates
        and inserts to be committed
        Queries vault to grab RDS credentials

        Args:
            return_connection (bool): If True will return both cursor and connection

        Returns:
            cursor object context, [connection]
        """
        DB_HOST_NAME = self.names.endpoint_db.rds
        logging.debug("DB Hostname is: {}".format(DB_HOST_NAME))

        logging.info('Getting MySQL parameters from Vault (slow) . . .')
        with self.vault() as vault:
            mysql_params = vault.read('secret/endpoint/django/db')

        logging.info('Tunneling to DB (slow) . . .')
        with self.tunnel(DB_HOST_NAME, mysql_params['port'], 'rds') as local_port:
            try:
                sql = connector.connect(
                    user=mysql_params['user'], password=mysql_params['password'], 
                    port=local_port, database=mysql_params['name']
                )
                cursor = sql.cursor()
                if return_connection:
                    yield cursor, sql
                else:
                    yield cursor
            finally:
                cursor.close()
                sql.close()

    def check_vault(self, timeout, exception=True):
        """Vault status check to see if Vault is accessible
        """
        ssh_errors = 8
        error_sleep = 30 # seconds
        while True:
            try:
                with vault_tunnel(self.keypair_file, self.bastions):
                    for sleep in gen_timeout(timeout, 15): # 15 second sleep
                        if self.vaults[0].status_check():
                            return True
                        time.sleep(sleep)

                    if exception:
                        msg = "Cannot connect to Vault after {} seconds".format(timeout)
                        raise exceptions.StatusCheckError(msg, self.vault_hostname)
                    else:
                        return False
            except SSHError as ex:
                ssh_errors -= 1
                if ssh_errors == 0:
                    if exception:
                        raise exceptions.StatusCheckError(str(ex), self.vault_hostname)
                    else:
                        return False
                else:
                    print("Error establishing SSH tunnel to Vault, waiting")
                    time.sleep(error_sleep)


    def check_keycloak(self, timeout, exception=True):
        """Keycloak status check to see if Keycloak is accessible
        """
        # DP ???: use the actual login url so the actual API is checked..
        #         (and parse response for 403 unauthorized vs any other error..)

        ssh_errors = 8
        error_sleep = 30 # seconds
        while True:
            try:
                with self.tunnel(self.names.auth.dns, 8080) as port:
                    # Could move to connecting through the ELB, but then KC will have to be healthy
                    URL = "http://localhost:{}/auth/".format(port)

                    for sleep in gen_timeout(timeout, 15): # 15 second sleep
                        try:
                            res = urlopen(URL)
                            if res.getcode() == 200:
                                return True
                        except:# HTTPError: Also seeing RemoteDisconnected
                            pass
                        time.sleep(sleep)

                    if exception:
                        msg = "Cannot connect to Keycloak after {} seconds".format(timeout)
                        raise exceptions.StatusCheckError(msg, self.names.auth.dns)
                    else:
                        return False
            except SSHError as ex:
                ssh_errors -= 1
                if ssh_errors == 0:
                    if exception:
                        raise exceptions.StatusCheckError(str(ex), self.names.auth.dns)
                    else:
                        return False
                else:
                    print("Error establishing SSH tunnel to Auth, waiting")
                    time.sleep(error_sleep)

    def check_url(self, url, timeout, exception=True):
        for sleep in gen_timeout(timeout, 15): # 15 second sleep
            try:
                res = urlopen(url)
                if res.getcode() == 200:
                    return True
            except HTTPError:
                pass
            time.sleep(sleep)

        if exception:
            msg = "Cannot connect to URL after {} seconds".format(timeout)
            raise exceptions.StatusCheckError(msg, url)
        else:
            return False

    def check_django(self, machine, manage_py, exception=True):
        cmd = "sudo python3 {} check 2> /dev/null > /dev/null".format(manage_py) # suppress all output

        with self.ssh(machine) as ssh:
            ret = ssh(cmd)
            if exception and ret != 0:
                msg = "Problem with the {}'s Django configuration".format(machine)
                raise exceptions.StatusCheckError(msg, machine + "." + self.domain)

            return ret == 0 # 0 - no issues, 1 - problems

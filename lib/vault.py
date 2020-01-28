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

import os
import glob
import hvac
import json
import time
from pprint import pprint
import traceback

from .exceptions import VaultError

VAULT_TOKEN = "vault_token"
VAULT_KEY = "vault_key."

VAULT_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "vault"))
POLICY_DIR = os.path.join(VAULT_DIR, "policies")
PRIVATE_DIR = os.path.join(VAULT_DIR, "private")

class Vault(object):
    def __init__(self, machine, ip = None, proxy = True):
        # If the machine is X.vault.vpc.boss remove the X.
        if machine and machine.count(".") == 3:
            self.machine = machine.split(".", 1)[1]
        else:
            self.machine = machine
        self.ip = ip

        # if in cluster mode, is_authenticated will http redirect to the cluster leader
        #client = hvac.Client(url="http://localhost:8200")#, allow_redirects=False)
        if ip is not None:
            host = ip
        elif machine is not None:
            host = self.machine
        else:
            host = "localhost"

        self.url = "http://{}:8200".format(host)
        if proxy:
            self.proxy = {"http": "http://localhost:3128"}
        else:
            self.proxy = {} # DP XXX: {} or None???

    def path(self, filename):
        """Get the complete file path for given machine's private file.
        Args:
            filename (string) : Name of the machine's private file
        Returns:
            (string) : Complete file path
        """

        machine = self.machine if self.machine else ""

        path = os.path.join(PRIVATE_DIR, machine, filename)
        os.makedirs(os.path.dirname(path), exist_ok = True)

        return path

    def connect(self, read_token = None):
        client = hvac.Client(url=self.url, proxies=self.proxy)

        if read_token is not None:
            token_file = self.path(read_token)
            if not os.path.exists(token_file):
                raise VaultError("Token file '{}' doesn't exist".format(token_file))

            with open(token_file, "r") as fh:
                client.token = fh.read()
                try:
                    if not client.is_authenticated():
                        raise VaultError("Vault token is not valid, cannot communicate with the Vault")
                except:
                    raise
        return client

    def status_check(self):
        """Check to see that Vault is up and available. Not checking the configuration
        status of Vault, just that it is ready to receive commands.
        """
        try:
            client = self.connect()
            client.sys.is_initialized() # make an actual network connection
            return True
        except:
            return False

    def shell(self):
        """Create a connection to Vault and then drop the user into an interactive
        shell (just like the python interperter) with 'client' holding the Vault
        connection object.
        """
        import code
        client = self.connect(VAULT_TOKEN)
        code.interact(local=locals())

    def initialize(self, account_id, secrets = 1, threshold = 1):
        """Initialize a Vault. Connect using get_client() and if the Vault is not
        initialized then initialize it with 1 recovery key (and only requiring the
        1 key when used). The recovery key is stored as VAULT_KEY and root token
        is stored as VAULT_TOKEN.

        After initializing the Vault it is unsealed for use and vault-configure
        is called.

        Note: This expects Vault to be configured using a `seal` stanza. If it is
              not initialization will fail.

        Args:
            account_id (str) : AWS Account ID that Vault is running under, passed to configure()
            secrets (int) : Total number of secrets to split the master key into
            threshold (int) : The number of secrets required to reconstruct the master key
        """

        client = self.connect()
        if client.sys.is_initialized():
            print("Vault is already initialized")
            if client.sys.is_sealed():
                print("Unsealing Vault")
                self.unseal()
            else:
                print("Vault already unsealed")
        else:
            print("Initializing with {} secrets and {} needed to unseal".format(secrets, threshold))
            result = client.sys.initialize(secret_shares=1,
                                           secret_threshold=1,
                                           stored_shares=1,
                                           recovery_shares=secrets,
                                           recovery_threshold=threshold)

            token_file = self.path(VAULT_TOKEN)
            key_file = self.path(VAULT_KEY)
            with open(token_file, "w") as fh:
                fh.write(result["root_token"])
            for i in range(secrets):
                with open(key_file + str(i+1), "w") as fh:
                    fh.write(result["recovery_keys"][i])

            # DP TODO: refactor code so that the root token is revoked after configuration?
            # DP ???: If no root token, how to auth for populating future values?
            print()
            print("========= WARNING WARNING WARNING =========")
            print("= Vault root token and recovery keys were =")
            print("= written to disk. PROTECT these files.   =")
            print("========= WARNING WARNING WARNING =========")
            print()

        # DP NOTE: When using the DynamoDB backend it is common for right after
        #          initializing for requests to Vault to response with the error
        #          > local node not active but active cluster node not found <
        #          If given a little bit of time Vault will respond successfully
        #          to requests

        def poll():
            """Check to see if Vault responds to a request without an error"""
            try:
                self.connect(VAULT_TOKEN).sys.list_enabled_audit_devices()
                return True
            except hvac.exceptions.InternalServerError as ex:
                if str(ex) == 'local node not active but active cluster node not found':
                    return False
                raise

        print("Waiting for Vault to finish initialization ", end='', flush=True)
        step, remaining = 10, 60
        while remaining >= 0:
            if poll():
                break

            print(".", end='', flush=True)
            remaining -= step
            time.sleep(step)
        if remaining < 0:
            raise Exception("Vault not finished initializing")
        print(" done")

        self.configure(account_id)

    def configure(self, account_id):
        """A companion function that will configure a newly initialized Vault
        as needed for BOSS. This includes:
            * Configuring the Audit Backend
            * Adding all of the policies from policies/*.hcl
            * Configure the AWS backend (if there are AWS credentials to use)
            * Configure AWS backend roles from policies/*.iam

        Args:
            account_id (str) : AWS Account ID that Vault is running under, used when binding
                               AWS roles to Vault policies in the AWS authentication backend
        """
        print("Configuring Vault")
        client = self.connect(VAULT_TOKEN)

        # Audit Backend
        if 'syslog/' not in client.sys.list_enabled_audit_devices():
            audit_options = {
                'log_raw': 'True',
            }
            client.sys.enable_audit_device('syslog', options=audit_options)
        else:
            print("audit_backend already created.")

        # Policies
        policies = []
        path = os.path.join(POLICY_DIR, "*.hcl")
        for policy in glob.glob(path):
            name = os.path.basename(policy).split('.')[0]
            policies.append(name)
            with open(policy, 'r') as fh:
                client.sys.create_or_update_policy(name, fh.read())

        # AWS Authentication Backend
        # Enable AWS auth in Vault
        if 'aws/' not in client.sys.list_auth_methods():
            try:
                client.sys.enable_auth_method('aws')
            except Exception as e:
                raise VaultError("Error while enabling auth back end. {}".format(e))
        else:
            print("aws auth backend already created.")

        #Define policies and arn                                     
        arn = 'arn:aws:iam::{}:instance-profile/'.format(account_id)

        #For each policy configure the policies on a role of the same name
        for policy in policies:
            client.create_ec2_role(policy,
                                   bound_iam_instance_profile_arn = arn + policy,
                                   policies = policy,
                                   mount_point = 'aws')
            print('Successful write to aws/role/' + policy)
        
        # AWS Secret Backend
        if 'aws/' not in client.sys.list_mounted_secrets_engines():
            try:
                client.sys.enable_secrets_engine('aws')
            except Exception as e:
                raise VaultError('Error while enabling secret back end. {}'.format(e))
        else:
            print("aws secret backend already created.")

        path = os.path.join(POLICY_DIR, "*.iam")
        for iam in glob.glob(path):
            name = os.path.basename(iam).split('.')[0]
            with open(iam, 'r') as fh:
                # if we json parse the file first we can use the duplicate key trick for comments
                client.secrets.aws.create_or_update_role(name, 'iam_user', policy_document = fh.read())

    def set_policy(self, name, policy):
        """Create or Update a policy

        Used by processes to add or update policies after Vault has been
        initially configured.
        """
        client = self.connect(VAULT_TOKEN)
        client.set_policy(name, policy)

    def list_policies(self):
        """List all policies

        Used by processes to add or update policies after Vault has been
        initially configured.
        """
        client = self.connect(VAULT_TOKEN)
        return client.list_policies()

    def unseal(self):
        """Unseal a sealed Vault. Connect using get_client() and if the Vault is
        not sealed read all of the keys defined by VAULT_KEY and unseal.

        If there are not enough keys to completely unseal the Vault, print a
        status message about how many more keys are required to finish the
        process.
        """

        client = self.connect()
        if not client.sys.is_sealed():
            print("Vault is already unsealed")
            return 0

        key_file = self.path(VAULT_KEY)
        keys = []
        for f in glob.glob(key_file + "*"):
            with open(f, "r") as fh:
                keys.append(fh.read())

        if len(keys) == 0:
            raise VaultError("Could not locate any key files, not unsealing")

        res = client.sys.submit_unseal_keys(keys)
        if res['sealed']:
            p = res['progress']
            t = res['t']
            print("Vault partly unsealed, {} of {} needed keys entered".format(p,t))
            print("Enter {} more keys to finish unsealing the vault". format(t-p))
            return (t-p)
        else:
            print("Vault unsealed")
            return 0

    def seal(self):
        """Seal an unsealed Vault. Connect using get_client(True) and if the Vault
        is unsealed, seal it.

        Used to quickly protect a Vault without having to stop the Vault service
        on a protected VM.
        """

        client = self.connect(VAULT_TOKEN)
        if client.sys.is_sealed():
            print("Vault is already sealed")
            return

        client.sys.seal()
        print("Vault is sealed")

    def status(self):
        """Print the status of a Vault. Connect using get_client(True) and print
        the status of the following items (if available):
         * Initializing status
         * Seal status
         * Key status
         * High Availability status
         * Secret backends
         * Policies
         * Audit backends
         * Auth backends
        """

        client = self.connect()
        if not client.sys.is_initialized():
            print("Vault is not initialized")
            return
        else:
            print("Vault is initialized")

        if client.sys.is_sealed():
            print("Vault is sealed")
            print(client.seal_status)
            return
        else:
            print("Vault is unsealed")

        # read in the Vault access token
        client = self.connect(VAULT_TOKEN)
        print()
        print("Key Status")
        print(json.dumps(client.key_status))

        print()
        print("HA Status")
        print(json.dumps(client.ha_status))

        print()
        print("Secret Backends")
        print(json.dumps(client.sys.list_mounted_secrets_engines(), indent=True))

        print()
        print("Policies")
        print(json.dumps(client.sys.list_policies()))

        print()
        print("Audit Backends")
        print(json.dumps(client.sys.list_enabled_audit_devices(), indent=True))

        print()
        print("Auth Backends")
        print(json.dumps(client.sys.list_auth_methods(), indent=True))

    def provision(self, policy):
        """Create a new Vault access token.

        Args:
            policy (string) : Name of the policy to attach to the new token

        Returns:
            (string) : String containing the new Vault token
        """
        client = self.connect(VAULT_TOKEN)
        token = client.create_token(policies = [policy])
        return token["auth"]["client_token"]

    def revoke(self, token):
        """Revoke a Vault access token.

        Args:
            token (string) : String containing the Vault token to revoke
        """
        client = self.connect(VAULT_TOKEN)
        client.revoke_token(token)

    def revoke_secret(self, lease_id):
        """Revoke a Vault lease

        Args:
            lease_id (string) : String containing the Vault lease id to revoke
        """
        client = self.connect(VAULT_TOKEN)
        client.sys.revoke_secret(lease_id)

    def revoke_secret_prefix(self, prefix):
        """Revoke a Vault secret by prefix

        Args:
            prefix (string) : String containing the Vault secret prefix to revoke
        """
        client = self.connect(VAULT_TOKEN)
        client.sys.revoke_secret_prefix(prefix)

    def write(self, path, **kwargs):
        """A generic method for writing data into Vault.

            Note: vault-write will override any data already existing at path.
                  There is vault-update that will update data at path instead.

        Args:
            path (string) : Vault path to write data to
            kwargs : Key value pairs to store at path
        """
        client = self.connect(VAULT_TOKEN)
        client.write(path, **kwargs)

    def update(self, path, **kwargs):
        """A generic method for adding/updating data to/in Vault.

        Args:
            path (string) : Vault path to write data to
            kwargs : Key value pairs to store at path
        """
        client = self.connect(VAULT_TOKEN)

        existing = client.read(path)
        if existing is None:
            existing = {}
        else:
            existing = existing["data"]

        existing.update(kwargs)

        client.write(path, **existing)

    def read(self, path):
        """A generic method for reading data from Vault.

        Args:
            path (string) : Vault path to read data from
        """
        client = self.connect(VAULT_TOKEN)
        return client.read(path)

    def list(self, path):
        """A generic method for listing data from Vault.

        Args:
            path (string) : Vault path to list data from
        """
        client = self.connect(VAULT_TOKEN)
        return client.list(path)

    def delete(self, path):
        """A generic method for deleting data from Vault.

        Args:
            path (string) : Vault path to delete all data from
        """
        client = self.connect(VAULT_TOKEN)
        client.delete(path)

    def export(self, path):
        """A generic method for reading all of the paths and keys from Vault.

        Args:
            path (string) : Vault path to dump data from
        """
        if path[-1] != '/':
            path += '/'

        rtn = {}

        # DP NOTE: not using self.read becuase of the different token needed
        client = self.connect(VAULT_TOKEN)
        results =  client.read(path[:-1])
        if results is not None:
            rtn[path[:-1]] = results['data']

        results = client.list(path)
        for key in results['data']['keys']:
            key = path + key
            if key[-1] == '/':
                data = self.export(key)
                rtn.update(data)
            else:
                # DP NOTE: This will currently do a duplicate read if
                #          data is stored at key and in paths under
                #          key
                #          To prevent this, check to see if (key + '/') is in keys
                data = self.read(key)
                rtn[key] = data['data']

        return rtn

    def import_(self, exported, update=False):
        """A generic method for writing / updating data in multiple paths in Vault.

        Args:
            exported (dict): Dict of Vault path and dict of key / values to store at the path
            update (bool): If an Update should be done or if a Write should be done
        """
        for path in exported:
            kv = exported[path]
            fn = self.update if update else self.write
            fn(path, **kv)

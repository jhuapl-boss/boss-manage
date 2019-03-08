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
from pprint import pprint
import traceback

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
                raise Exception("Token file '{}' doesn't exist".format(token_file))

            with open(token_file, "r") as fh:
                client.token = fh.read()
                try:
                    if not client.is_authenticated():
                        raise Exception("Vault token is not valid, cannot communicate with the Vault")
                except:
                    raise
        return client

    def status_check(self):
        """Check to see that Vault is up and available. Not checking the configuration
        status of Vault, just that it is ready to receive commands.
        """
        try:
            client = self.connect()
            client.is_initialized() # make an actual network connection
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

    def initialize(self, secrets = 5, threashold = 3):
        """Initialize a Vault. Connect using get_client() and if the Vault is not
        initialized then initialize it with 5 secrets and a threashold of 3. The
        keys are stored as VAULT_KEY and root token is stored as VAULT_TOKEN.

        After initializing the Vault it is unsealed for use and vault-configure is called.

        Args:
            secrets (int) : Total number of secrets to split the master key into
            threashold (int) : The number of secrets required to reconstruct the master key
        """

        client = self.connect()
        if client.is_initialized():
            print("Vault is already initialized")
            if client.is_sealed():
                print("Unsealing Vault")
                self.unseal()
            else:
                print("Vault already unsealed")
        else:
            print("Initializing with {} secrets and {} needed to unseal".format(secrets, threashold))
            result = client.initialize(secrets, threashold)

            token_file = self.path(VAULT_TOKEN)
            key_file = self.path(VAULT_KEY)
            with open(token_file, "w") as fh:
                fh.write(result["root_token"])
            for i in range(secrets):
                with open(key_file + str(i+1), "w") as fh:
                    fh.write(result["keys"][i])

            print()
            print("======== WARNING WARNING WARNING ========")
            print("= Vault root token and unseal keys were =")
            print("= written to disk. PROTECT these files. =")
            print("======== WARNING WARNING WARNING ========")

            print()
            print("Unsealing Vault")
            client.unseal_multi(result["keys"])

        self.configure()

    def configure(self):
        """A companion function that will configure a newly initialized Vault
        as needed for BOSS. This includes:
            * Configuring the Audit Backend
            * Adding all of the policies from policies/*.hcl
            * Creating a provisioner token with all of the policies added
                - Required so that the provisioner token can issue tokens
                  for any policy
            * Configure the AWS backend (if there are AWS credentials to use)
            * Configure AWS backend roles from policies/*.iam
            * Configure the PKI backend (if there is a certificate to use)
            * Configure PKI backend roles from policies/*.pki

        Args:
            machine (None|string) : hostname of the machine, used for reading/saving unique data
        """
        print("Configuring Vault")
        client = self.connect(VAULT_TOKEN)

        # Audit Backend
        audit_options = {
            'low_raw': 'True',
        }
        try:
            client.enable_audit_backend('syslog', options=audit_options)
        except hvac.exceptions.InvalidRequest as ex:
            print("audit_backend already created.")

        # Policies
        provisioner_policies = []
        path = os.path.join(POLICY_DIR, "*.hcl")
        for policy in glob.glob(path):
            name = os.path.basename(policy).split('.')[0]
            with open(policy, 'r') as fh:
                client.set_policy(name, fh.read())
            # Add every policy to the provisioner, as it has to have the
            # superset of any policies that it will provision
            provisioner_policies.append(name)

        # AWS Authentication Backend
        #Enable AWS auth in Vault
        if 'aws' not in client.list_auth_backends():
            try:
                client.enable_auth_backend('aws')
            except Exception as e:
                raise Exception("Error while enabling auth back end: " + e)
        else:
            print("aws auth backend already created.")

        #Define policies and arn                                     
        policies = [p for p in provisioner_policies if p not in ('provisioner',)]
        arn = 'arn:aws:iam::{}:instance-profile/'.format(os.environ['AWS_ACCOUNT'])
        #TODO: Find a temporary way of storing the aws account number
        #For each policy configure the policies on a role of the same name
        for policy in policies:
            client.write('/auth/aws/role/' + policy, auth_type='ec2', bound_iam_instance_profile_arn= arn + policy, policies=policy)
            print('Successful write to aws/role/' + policy)
        
        # AWS Secret Backend
        if 'aws' not in client.list_secret_backends():
            try:
                client.enable_secret_backend('aws')
            except Exception as e:
                raise Exception('Error while enabling secret back end: ' + e)
        else:
            print("aws secret backend already created.")

        path = os.path.join(POLICY_DIR, "*.iam")
        for iam in glob.glob(path):
            name = os.path.basename(iam).split('.')[0]
            with open(iam, 'r') as fh:
                # if we json parse the file first we can use the duplicate key trick for comments
                client.write("aws/roles/" + name, policy = fh.read())

        # PKI Backend
        """
        if True: # Disabled until we either have a CA cert or can generate a CA
            print("Vault PKI cert file does not exist, skipping configuration of PKI secret backend")
        else:
            client.enable_secret_backend('pki')
            # Generate a self signed certificate for CA
            print("Generating self signed CA")
            response = client.write("pki/root/generate/internal", common_name=aws_creds["domain"])
            with open(get_path(machine, "ca.pem"), 'w') as fh:
                fh.write(response["data"]["certificate"])

            # Should we configure CRL?

            path = os.path.join(_CURRENT_DIR, "policies", "*.pki")
            for pki in glob.glob(path):
                name = os.path.basename(pki).split('.')[0]
                with open(pki, 'r') as fh:
                    keys = json.load(fh)
                    client.write("aws/roles/" + name, **keys)
        """

    def unseal(self):
        """Unseal a sealed Vault. Connect using get_client() and if the Vault is
        not sealed read all of the keys defined by VAULT_KEY and unseal.

        If there are not enough keys to completely unseal the Vault, print a
        status message about how many more keys are required to finish the
        process.
        """

        client = self.connect()
        if not client.is_sealed():
            print("Vault is already unsealed")
            return 0

        key_file = self.path(VAULT_KEY)
        keys = []
        for f in glob.glob(key_file + "*"):
            with open(f, "r") as fh:
                keys.append(fh.read())

        if len(keys) == 0:
            raise Exception("Could not locate any key files, not unsealing")

        res = client.unseal_multi(keys)
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
        if client.is_sealed():
            print("Vault is already sealed")
            return

        client.seal()
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
        if not client.is_initialized():
            print("Vault is not initialized")
            return
        else:
            print("Vault is initialized")

        if client.is_sealed():
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
        print(json.dumps(client.list_secret_backends(), indent=True))

        print()
        print("Policies")
        print(json.dumps(client.list_policies()))

        print()
        print("Audit Backends")
        print(json.dumps(client.list_audit_backends(), indent=True))

        print()
        print("Auth Backends")
        print(json.dumps(client.list_auth_backends(), indent=True))

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
        client.revoke_secret(lease_id)

    def revoke_secret_prefix(self, prefix):
        """Revoke a Vault secret by prefix

        Args:
            prefix (string) : String containing the Vault secret prefix to revoke
        """
        client = self.connect(VAULT_TOKEN)
        client.revoke_secret_prefix(prefix)

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

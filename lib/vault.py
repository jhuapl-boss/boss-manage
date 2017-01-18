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

VAULT_TOKEN = "vault_token"
VAULT_KEY = "vault_key."
PROVISIONER_TOKEN = "provisioner_token"


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
        client = connect(VAULT_TOKEN)
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
        client.enable_audit_backend('syslog', options=audit_options)

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

        token_file = self.path(PROVISIONER_TOKEN)
        token = client.create_token(policies=provisioner_policies)
        with open(token_file, "w") as fh:
            fh.write(token['auth']['client_token'])

        # Read AWS credentials file
        vault_aws_creds = os.path.join(PRIVATE_DIR, "vault_aws_credentials")
        if os.path.exists(vault_aws_creds):
            with open(vault_aws_creds, "r") as fh:
                aws_creds = json.load(fh)
        else:
            aws_creds = None

        # AWS Authentication Backend
        if aws_creds is None:
            print("Vault AWS credentials files does nto exist, skipping configuration of AWS-EC2 authentication backend")
        else:
            client.enable_auth_backend('aws-ec2')
            client.write('auth/aws-ec2/config/client', access_key = aws_creds["aws_access_key"],
                                                       secret_key = aws_creds["aws_secret_key"])

            arn_prefix = 'arn:aws:iam::{}:instance-profile/'.format(aws_creds["aws_account"])
            policies = [p for p in provisioner_policies if p not in ('provisioner',)]
            for policy in policies:
                client.write('/auth/aws-ec2/role/' + policy, policies = policy,
                                                             bound_iam_role_arn = arn_prefix + policy)

        # AWS Secret Backend
        if aws_creds is None:
            print("Vault AWS credentials file does not exist, skipping configuration of AWS secret backend")
        else:
            client.enable_secret_backend('aws')
            client.write("aws/config/root", access_key = aws_creds["aws_access_key"],
                                            secret_key = aws_creds["aws_secret_key"],
                                            region = aws_creds.get("aws_region", "us-east-1"))
            client.write("aws/config/lease", lease = aws_creds.get("lease_duration", "1h"),
                                             lease_max = aws_creds.get("lease_max", "24h")) # DP TODO finalize default values

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
        client = self.connect(PROVISIONER_TOKEN)
        token = client.create_token(policies = [policy])
        return token["auth"]["client_token"]

    def revoke(self, token):
        """Revoke a Vault access token.

        Args:
            token (string) : String containing the Vault token to revoke
        """
        client = self.connect(PROVISIONER_TOKEN)
        client.revoke_token(token)

    def write(self, path, **kwargs):
        """A generic method for writing data into Vault.

            Note: vault-write will override any data already existing at path.
                  There is vault-update that will update data at path instead.

        Args:
            path (string) : Vault path to write data to
            kwargs : Key value pairs to store at path
        """
        client = self.connect(PROVISIONER_TOKEN)
        client.write(path, **kwargs)

    def update(self, path, **kwargs):
        """A generic method for adding/updating data to/in Vault.

        Args:
            path (string) : Vault path to write data to
            kwargs : Key value pairs to store at path
        """
        client = self.connect(PROVISIONER_TOKEN)

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
        client = self.connect(PROVISIONER_TOKEN)
        return client.read(path)

    def list(self, path):
        """A generic method for listing data from a Vault secret backend.

        Args:
            path (string) : Vault path to list data at
        """
        client = self.connect(VAULT_TOKEN)
        return client.list(path)

    def delete(self, path):
        """A generic method for deleting data from Vault.

        Args:
            path (string) : Vault path to delete all data from
        """
        client = self.connect(PROVISIONER_TOKEN)
        client.delete(path)


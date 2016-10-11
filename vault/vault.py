#!/usr/bin/env python3

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

"""A library and script for manipulating a Vault instance.

VAULT_TOKEN : The location to store and read the Vault's root token
VAULT_KEY : The prefix location to store and read the Vault's crypto keys
NEW_TOKEN : The location to store a new new access token for the Vault
PROVISIONER_TOKEN : The location to store and read the Vault token for provisioning

COMMANDS : A dictionary of available commands and the functions to call

Author:
    Derek Pryor <Derek.Pryor@jhuapl.edu>
"""

import argparse
import sys
import os
import glob
import hvac
import json
import uuid
from pprint import pprint

"""Location to store and read the Vault's Root Token"""
VAULT_TOKEN = "vault_token"
VAULT_KEY = "vault_key."
NEW_TOKEN = "new_token"
PROVISIONER_TOKEN = "provisioner_token"

_CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))
def get_path(machine, filename):
    """Get the complete file path for given machine's private file.
    Args:
        machine (None|string) : Either None or the machine's full hostname
        filename (string) : Name of the machine's private file
    Returns:
        (string) : Complete file path
    """
    if machine is None:
        machine = ""

    path = os.path.join(_CURRENT_DIR, "private", machine, filename)

    os.makedirs(os.path.dirname(path), exist_ok = True)

    return path

def get_client(read_token = None, machine = None, ip = None):
    """Open a connection to the Vault located at http://localhost:8200

    If read_token is not None then read the token from get_path(machine, read_token)
    and verify that the client is authenticated to the Vault.

    Exits (sys.exit) if read_token does not exists
    Exits (sys.exit) if read_token does not contain a valid token
    """

    # If the machine is X.vault.vpc.boss remove the X.
    if machine.count(".") == 3:
        machine = machine.split(".", 1)[1]

    # if in cluster mode, is_authenticated will http redirect to the cluster leader
    #client = hvac.Client(url="http://localhost:8200")#, allow_redirects=False)
    host = "localhost"
    if ip is not None:
        host = ip
    elif machine is not None:
        host = machine
    url = "http://{}:8200".format(host)
    client = hvac.Client(url=url, proxies={"http": "http://localhost:3128"})

    if read_token is not None:
        token_file = get_path(machine, read_token)
        if not os.path.exists(token_file):
            print("Need the root token to communicate with the Vault, exiting...")
            sys.exit(1) # TODO DP: need a better exit if running by another script...

        with open(token_file, "r") as fh:
            client.token = fh.read()
            try:
                if not client.is_authenticated():
                    print("Vault token is not valid, cannot communicate with the Vault, exiting...")
                    sys.exit(1) # TODO DP: need a better exit if running by another script...
            except:
                raise
                print("Not connected to primary Vault server, not redirecting")
                return None # TODO DP: figure out a better response, as above

    return client

def vault_init(machine = None, ip = None, secrets = 5, threashold = 3):
    """Initialize a Vault. Connect using get_client() and if the Vault is not
    initialized then initialize it with 5 secrets and a threashold of 3. The
    keys are stored as VAULT_KEY and root token is stored as VAULT_TOKEN.

    After initializing the Vault it is unsealed for use and vault-configure is called.

    Args:
        machine (None|string) : hostname of the machine, used for saving unique data
        secrets (int) : Total number of secrets to split the master key into
        threashold (int) : The number of secrets required to reconstruct the master key
    """

    client = get_client(machine = machine, ip = ip)
    if client.is_initialized():
        print("Vault is already initialized")
        if client.is_sealed():
            vault_unseal(machine, ip)
        return

    print("Initializing with {} secrets and {} needed to unseal".format(secrets, threashold))
    result = client.initialize(secrets, threashold)

    token_file = get_path(machine, VAULT_TOKEN)
    key_file = get_path(machine, VAULT_KEY)
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

    print()
    print("Configuring Vault")
    vault_configure(machine, ip)

def vault_configure(machine = None, ip = None):
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
    client = get_client(read_token = VAULT_TOKEN, machine = machine, ip = ip)

    # Audit Backend
    audit_options = {
        'low_raw': 'True',
    }
    client.enable_audit_backend('syslog', options=audit_options)

    # Policies
    provisioner_policies = []
    path = os.path.join(_CURRENT_DIR, "policies", "*.hcl")
    for policy in glob.glob(path):
        name = os.path.basename(policy).split('.')[0]
        with open(policy, 'r') as fh:
            client.set_policy(name, fh.read())

        # Add every policy to the provisioner, as it has to have the
        # superset of any policies that it will provision
        provisioner_policies.append(name)

    token_file = get_path(machine, PROVISIONER_TOKEN)
    token = client.create_token(policies=provisioner_policies)
    with open(token_file, "w") as fh:
        fh.write(token['auth']['client_token'])

    # Read AWS credentials file
    vault_aws_creds = os.path.join(_CURRENT_DIR, "private", "vault_aws_credentials")
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

        path = os.path.join(_CURRENT_DIR, "policies", "*.iam")
        for iam in glob.glob(path):
            name = os.path.basename(iam).split('.')[0]
            with open(iam, 'r') as fh:
                # if we json parse the file first we can use the duplicate key trick for comments
                client.write("aws/roles/" + name, policy = fh.read())

    # PKI Backend
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

def vault_shell(machine = None, ip = None):
    """Create a connection to Vault and then drop the user into an interactive
    shell (just like the python interperter) with 'client' holding the Vault
    connection object.

    Args:
        machine (None|string) : hostname of the machine, used for reading unique data
    """
    import code

    client = get_client(read_token = VAULT_TOKEN, machine = machine, ip = ip)

    code.interact(local=locals())

def vault_unseal(machine = None, ip = None):
    """Unseal a sealed Vault. Connect using get_client() and if the Vault is
    not sealed read all of the keys defined by VAULT_KEY and unseal.

    If there are not enough keys to completely unseal the Vault, print a
    status message about how many more keys are required to finish the
    process.

    Args:
        machine (None|string) : hostname of the machine, used for reading unique data
    """

    client = get_client(machine = machine, ip = ip)
    if not client.is_sealed():
        print("Vault is already unsealed")
        return

    key_file = get_path(machine, VAULT_KEY)
    keys = []
    for f in glob.glob(key_file + "*"):
        with open(f, "r") as fh:
            keys.append(fh.read())

    if len(keys) == 0:
        print("Could not locate any key files, not unsealing")
        return

    res = client.unseal_multi(keys)
    if res['sealed']:
        p = res['progress']
        t = res['t']
        print("Vault partly unsealed, {} of {} needed keys entered".format(p,t))
        print("Enter {} more keys to finish unsealing the vault". format(t-p))
    else:
        print("Vault unsealed")

def vault_seal(machine = None, ip = None):
    """Seal an unsealed Vault. Connect using get_client(True) and if the Vault
    is unsealed, seal it.

    Used to quickly protect a Vault without having to stop the Vault service
    on a protected VM.

    Args:
        machine (None|string) : hostname of the machine, used for reading unique data
    """

    client = get_client(read_token = VAULT_TOKEN, machine = machine, ip = ip)
    if client.is_sealed():
        print("Vault is already sealed")
        return

    client.seal()
    print("Vault is sealed")

def vault_status(machine = None, ip = None):
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

    Args:
        machine (None|string) : hostname of the machine, used for reading unique data
    """

    client = get_client(machine = machine, ip = ip)
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
    client = get_client(read_token = VAULT_TOKEN, machine = machine, ip = ip)
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

def vault_provision(policy, machine = None, ip = None):
    """Create a new Vault access token.

    Args:
        policy (string) : Name of the policy to attach to the new token
        machine (None|string) : hostname of the machine, used for reading unique data

    Returns:
        (string) : String containing the new Vault token
    """
    client = get_client(read_token = PROVISIONER_TOKEN, machine = machine, ip = ip)

    token = client.create_token(policies = [policy])
    return token["auth"]["client_token"]

def _vault_provision(machine = None, ip = None, policy = None):
    """Create a new Vault access token.

    Command line version of vault-provision. If policy is not given, then
    prompt the user for the policy and then save to NEW_TOKEN file.

    Args:
        machine (None|string) : hostname of the machine, used for reading unique data
        policy (None|string) : Name of the policy to attach to the new token
                               If policy is None then the user is prompted for the policy name
    """
    if policy is None:
        policy = input("policy: ")
    token = vault_provision(policy, machine, ip)

    token_file = get_path(machine, NEW_TOKEN)
    print("Provisioned Token saved to {}".format(token_file))
    with open(token_file, "w") as fh:
        fh.write(token)

def vault_revoke(token, machine = None, ip = None):
    """Revoke a Vault access token.

    Args:
        token (string) : String containing the Vault token to revoke
        machine (None|string) : hostname of the machine, used for reading unique data
    """
    client = get_client(read_token = PROVISIONER_TOKEN, machine = machine, ip = ip)

    client.revoke_token(token)

def _vault_revoke(machine = None, ip = None, token = None):
    """Revoke a Vault access token.

    Command line version of vault-revoke. If token is not given, then
    prompt the user for the token to revoke

    Args:
        machine (None|string) : hostname of the machine, used for reading unique data
        token (None|string) : String containing the Vault token to revoke
                              If token is None then the user is prompted for the token value
    """
    if token is None:
        token = input("token: ") # prompt for token or ready fron NEW_TOKEN (or REVOKE_TOKEN)?
    vault_revoke(token, machine, ip)

def vault_write(path, machine = None, ip = None, **kwargs):
    """A generic method for writing data into Vault.

        Note: vault-write will override any data already existing at path.
              There is vault-update that will update data at path instead.

    Args:
        path (string) : Vault path to write data to
        machine (None|string) : hostname of the machine, used for reading unique data
        kwargs : Key value pairs to store at path
    """
    client = get_client(read_token = PROVISIONER_TOKEN, machine = machine, ip = ip)
    client.write(path, **kwargs)

def _vault_write(machine = None, ip = None, path = None, *args):
    """A generic method for writing data into Vault.

    Command line version of vault-write. If the path or arguments are not given,
    then prompt the user for the path and data to store.

        Note: vault-write will override any data already existing at path.
              There is vault-update that will update data at path instead.

    Args:
        machine (None|string) : hostname of the machine, used for reading unique data
        path (None|string) : Vault path to write data to
                             if path is None then the user is prompted for the Vault path
        args : List of "key=value" strings, that will be split and processed into a dict
               if args is empty, the user will be prompted (one key/value at a time)
               for the data to store at path.
    """
    if path is None:
        path = input("path: ")
    entries = {}
    if len(args) == 0:
        while True:
            entry = input("entry (key=value): ")
            if entry is None or entry == '':
                break
            key,val = entry.split("=")
            entries[key.strip()] = val.strip()
    else:
        for arg in args:
            key,val = arg.split("=")
            entries[key.strip()] = val.strip()

    vault_write(path, machine, ip, **entries)

def vault_update(path, machine = None, ip = None, **kwargs):
    """A generic method for adding/updating data to/in Vault.

    Args:
        path (string) : Vault path to write data to
        machine (None|string) : hostname of the machine, used for reading unique data
        kwargs : Key value pairs to store at path
    """
    client = get_client(read_token = PROVISIONER_TOKEN, machine = machine, ip = ip)

    existing = client.read(path)
    if existing is None:
        existing = {}
    else:
        existing = existing["data"]

    existing.update(kwargs)

    client.write(path, **existing)

def _vault_update(machine = None, ip = None, path = None, *args):
    """A generic method for adding/updating data to/in Vault.

    Command line version of vault-update. If the path or arguments are not given,
    then prompt the user for the path and data to store.

    Args:
        machine (None|string) : hostname of the machine, used for reading unique data
        path (None|string) : Vault path to write data to
                             if path is None then the user is prompted for the Vault path
        args : List of "key=value" strings, that will be split and processed into a dict
               if args is empty, the user will be prompted (one key/value at a time)
               for the data to store at path.
    """
    if path is None:
        path = input("path: ")
    entries = {}
    if len(args) == 0:
        while True:
            entry = input("entry (key=value): ")
            if entry is None or entry == '':
                break
            key,val = entry.split("=")
            entries[key.strip()] = val.strip()
    else:
        for arg in args:
            key,val = arg.split("=")
            entries[key.strip()] = val.strip()

    vault_update(path, machine, ip, **entries)

def vault_read(path, machine = None, ip = None):
    """A generic method for reading data from Vault.

    Args:
        path (string) : Vault path to read data from
        machine (None|string) : hostname of the machine, used for reading unique data
    """
    client = get_client(read_token = PROVISIONER_TOKEN, machine = machine, ip = ip)
    return client.read(path)

def _vault_read(machine = None, ip = None, path = None):
    """A generic method for reading data from Vault.

    Command line version of vault-read. If the path is not given, then prompt
    the user for the path.

    Args:
        machine (None|string) : hostname of the machine, used for reading unique data
        path (string) : Vault path to read data from
                        if path is None then the user is prompted for the Vault path
    """

    if path is None:
        path = input("path: ")
    results = vault_read(path, machine, ip)
    pprint(results)

def vault_delete(path, machine = None, ip = None):
    """A generic method for deleting data from Vault.

    Args:
        path (string) : Vault path to delete all data from
        machine (None|string) : hostname of the machine, used for reading unique data
    """
    client = get_client(read_token = PROVISIONER_TOKEN, machine = machine, ip = ip)
    client.delete(path)

def _vault_delete(machine = None, ip = None, path = None):
    """A generic method for deleting data from Vault.

    Command line version of vault-delete. If the path is not given, then prompt
    the user for the path.

    Args:
        machine (None|string) : hostname of the machine, used for reading unique data
        path (string) : Vault path to delete all data from
                        if path is None then the user is prompted for the Vault path
    """
    if path is None:
        path = input("path: ")
    vault_delete(path, machine, ip)

COMMANDS = {
    "vault-init": vault_init,
    "vault-configure": vault_configure,
    "vault-unseal": vault_unseal,
    "vault-seal": vault_seal,
    "vault-status": vault_status,
    "vault-provision": _vault_provision,
    "vault-revoke": _vault_revoke,
    "vault-shell":vault_shell,
    "vault-write":_vault_write,
    "vault-update":_vault_update,
    "vault-read":_vault_read,
    "vault-delete":_vault_delete,
}

if __name__ == '__main__':
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    commands = list(COMMANDS.keys())
    commands_help = create_help("command supports the following:", commands)

    parser = argparse.ArgumentParser(description = "Script for manipulating Vault instances",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=commands_help)
    parser.add_argument("--machine", "-m", help = "The name of the Vault server, used to read/write tokens and keys.")
    parser.add_argument("command",
                        choices = commands,
                        metavar = "command",
                        help = "Command to execute")

    args = parser.parse_args()

    if args.command in COMMANDS:
        COMMANDS[args.command](args.machine)
    else:
        parser.print_usage()
        sys.exit(1)

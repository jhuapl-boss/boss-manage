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

VAULT_TOKEN - The location to store and read the Vault's root token
VAULT_KEY - The prefix location to store and read the Vault's crypto keys
NEW_TOKEN - The location to store a new new access token for the Vault

COMMANDS - A dictionary of available commands and the functions to call
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
    if machine is None:
        machine = ""

    path = os.path.join(_CURRENT_DIR, "private", machine, filename)

    os.makedirs(os.path.dirname(path), exist_ok = True)

    return path

def get_client(read_token = None, machine = None):
    """Open a connection to the Vault located at http://localhost:8200

    If read_token == True then read the token from VAULT_TOKEN and verify
    that the client is authenticated to the Vault.

    Exits (sys.exit) if read_token and VAULT_TOKEN does not exists
    Exits (sys.exit) if read_token and VAULT_TOKEN does not contain a valid
                     token
    """
    client = hvac.Client(url="http://localhost:8200")

    if read_token is not None:
        token_file = get_path(machine, read_token)
        if not os.path.exists(token_file):
            print("Need the root token to communicate with the Vault, exiting...")
            sys.exit(1)

        with open(token_file, "r") as fh:
            client.token = fh.read()
            if not client.is_authenticated():
                print("Vault token is not valid, cannot communicate with the Vault, exiting...")
                sys.exit(1)

    return client

def vault_init(machine = None, secrets = 5, threashold = 3):
    """Initialize a Vault. Connect using get_client() and if the Vault is not
    initialized then initialize it with 5 secrets and a threashold of 3. The
    keys are stored as VAULT_KEY and root token is stored as VAULT_TOKEN.

    After initializing the Vault it is unsealed for use.
    """

    client = get_client(machine = machine)
    if client.is_initialized():
        print("Vault is already initialized")
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
    vault_configure(machine)

def vault_configure(machine = None):
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
    """
    client = get_client(read_token = VAULT_TOKEN, machine = machine)

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

    # AWS Backend
    vault_aws_creds = os.path.join(_CURRENT_DIR, "private", "vault_aws_credentials")
    if not os.path.exists(vault_aws_creds):
        print("Vault AWS credentials file does not exist, skipping...")
    else:
        client.enable_secret_backend('aws')
        with open(vault_aws_creds, "r") as fh:
            creds = json.load(fh)
            client.write("aws/config/root", access_key = creds["aws_access_key"],
                                            secret_key = creds["aws_secret_key"],
                                            region = creds.get("aws_region", "us-east-1"))

        path = os.path.join(_CURRENT_DIR, "policies", "*.iam")
        for iam in glob.glob(path):
            name = os.path.basename(iam).split('.')[0]
            with open(iam, 'r') as fh:
                # if we json parse the file first we can use the duplicate key trick for comments
                client.write("aws/roles/" + name, policy = fh.read())

    # PKI Backend
    if True: # Disabled until we either have a CA cert or can generate a CA
        print("Vault PKI cert file does not exist, skipping...")
    else:
        client.enable_secret_backend('pki')
        # Generate a self signed certificate for CA
        print("Generating self signed CA")
        response = client.write("pki/root/generate/internal", common_name="boss.io")
        with open(get_path(machine, "ca.pem"), 'w') as fh:
            fh.write(response["data"]["certificate"])

        # Should we configure CRL?

        path = os.path.join(_CURRENT_DIR, "policies", "*.pki")
        for pki in glob.glob(path):
            name = os.path.basename(pki).split('.')[0]
            with open(pki, 'r') as fh:
                keys = json.load(fh)
                client.write("aws/roles/" + name, **keys)

def vault_shell(machine = None):
    """Create a connection to Vault and then drop the user into an interactive
    shell (just like the python interperter) with 'client' holding the Vault
    connection object.
    """
    import code

    client = get_client(read_token = VAULT_TOKEN, machine = machine)

    code.interact(local=locals())

def verify(machine = None):
    """Development function that gets updated when I need to script changes
    to Vault.
    """
    client = get_client(read_token = VAULT_TOKEN, machine = machine)

    token_file = get_path(machine, PROVISIONER_TOKEN)
    policy = "provisioner"

    if False:
        pprint(client.list_policies())
        pprint(client.read("/sys/policy/" + policy))

    if True:
        client.delete_policy(policy)
        with open("policies/{}.hcl".format(policy), "r") as fh:
            client.set_policy(policy, fh.read())

    if True:
        with open(token_file, 'r') as fh:
            result = client.revoke_token(fh.read())
        with open(token_file, 'w') as fh:
            result = client.create_token(policies=["provisioner","endpoint"])
            pprint(result)
            fh.write(result['auth']['client_token'])

    if False:
        with open(token_file, 'r') as fh:
            result = client.lookup_token(fh.read())
            pprint(result)

def vault_unseal(machine = None):
    """Unseal a sealed Vault. Connect using get_client() and if the Vault is
    not sealed read all of the keys defined by VAULT_KEY and unseal.

    If there are not enough keys to completely unseal the Vault, print a
    status message about how many more keys are required to finish the
    process.
    """

    client = get_client(machine = machine)
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

def vault_seal(machine = None):
    """Seal an unsealed Vault. Connect using get_client(True) and if the Vault
    is unsealed, seal it.

    Used to quickly protect a Vault without having to stop the Vault service
    on a protected VM.
    """

    client = get_client(read_token = VAULT_TOKEN, machine = machine)
    if client.is_sealed():
        print("Vault is already sealed")
        return

    client.seal()
    print("Vault is sealed")

def vault_status(machine = None):
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

    client = get_client(machine = machine)
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
    client = get_client(read_token = VAULT_TOKEN, machine = machine)
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

def vault_provision(policy, machine = None):
    """Create a new Vault access token. Connect using get_client(True),
    request a new access token (default policy), and save it to NEW_TOKEN.
    """
    client = get_client(read_token = PROVISIONER_TOKEN, machine = machine)

    token = client.create_token(policies = [policy])
    return token["auth"]["client_token"]

def _vault_provision(machine = None, policy = None):
    if policy is None:
        policy = input("policy: ")
    token = vault_provision(policy, machine)

    token_file = get_path(machine, NEW_TOKEN)
    print("Provisioned Token saved to {}".format(token_file))
    with open(token_file, "w") as fh:
        fh.write(token)

def vault_revoke(token, machine = None):
    """Revoke a Vault access token. Connect using get_client(True), read the
    token (using input()), and then revoke the token.
    """
    client = get_client(read_token = PROVISIONER_TOKEN, machine = machine)

    client.revoke_token(token)

def _vault_revoke(machine = None, token = None):
    if token is None:
        token = input("token: ") # prompt for token or ready fron NEW_TOKEN (or REVOKE_TOKEN)?
    vault_revoke(token, machine)

def vault_write(path, machine = None, **kwargs):
    """A generic method for writing data into Vault, for use by CloudFormation
    scripts.
    """
    client = get_client(read_token = PROVISIONER_TOKEN, machine = machine)
    client.write(path, **kwargs)

def _vault_write(machine = None, path = None, *args):
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

    vault_write(path, machine, **entries)

def vault_update(path, machine = None, **kwargs):
    """A generic method for updating data in Vault, for use by CloudFormation
    scripts.
    """
    client = get_client(read_token = PROVISIONER_TOKEN, machine = machine)

    existing = client.read(path)
    if existing is None:
        existing = {}
    else:
        existing = existing["data"]

    existing.update(kwargs)

    client.write(path, **existing)

def _vault_update(machine = None, path = None, *args):
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

    vault_update(path, machine, **entries)

def vault_read(path, machine = None):
    """A generic method for reading data from Vault, for use by CloudFormation
    scripts.
    """
    client = get_client(read_token = PROVISIONER_TOKEN, machine = machine)
    return client.read(path)

def _vault_read(machine = None, path = None):
    if path is None:
        path = input("path: ")
    results = vault_read(path, machine)
    pprint(results)

def vault_delete(path, machine = None):
    """A generic method for deleting data from Vault, for use by CloudFormation
    scripts.
    """
    client = get_client(read_token = PROVISIONER_TOKEN, machine = machine)
    client.delete(path)

def _vault_delete(machine = None, path = None):
    if path is None:
        path = input("path: ")
    vault_delete(path, machine)

COMMANDS = {
    "vault-init": vault_init,
    "vault-configure": vault_configure,
    "vault-unseal": vault_unseal,
    "vault-seal": vault_seal,
    "vault-status": vault_status,
    "vault-provision": _vault_provision,
    "vault-revoke": _vault_revoke,
    "verify":verify,
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

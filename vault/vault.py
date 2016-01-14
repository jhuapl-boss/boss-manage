#!/usr/bin/env python3

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
    client = get_client(read_token = VAULT_TOKEN, machine = machine)
    
    # Audit Backend
    audit_options = {
        'low_raw': 'True',
    }
    client.enable_audit_backend('syslog', options=audit_options)
    
    # Policies
    provisioner_policies = []
    for policy in glob.glob("policies/*.hcl"):
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
    # PKI Backend
    
def verify(machine = None):
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
        
def _vault_provision(machine = None):
    policy = input("policy: ")
    token = vault_provision(policy, machine)
    
    token_file = get_path(machine, NEW_TOKEN)
    with open(token_file, "w") as fh:
        fh.write(token)

def vault_revoke(token, machine = None):
    """Revoke a Vault access token. Connect using get_client(True), read the
    token (using input()), and then revoke the token.
    """
    client = get_client(read_token = PROVISIONER_TOKEN, machine = machine)
    
    client.revoke_token(token)
    
def _vault_revoke(machine = None):
    token = input("token: ") # prompt for token or ready fron NEW_TOKEN (or REVOKE_TOKEN)?
    vault_revoke(token, machine)
    
def vault_django(db_name, username, password, port, machine = None):
    """Provision a Vault with credentials for a Django webserver. Connect
    using get_client(True) and provision the following information:
     * Generate a secret key and store under 'secret/django secret_key=`
     * Prompt the user (using input()) for the
       - Database Name
       - Database Username
       - Database Password
       - Database Port
       and store under
       - 'secret/django/db name='
       - 'secret/django/db user='
       - 'secret/django/db password='
       - 'secret/django/db port='
    """
    client = get_client(read_token = PROVISIONER_TOKEN, machine = machine)
    
    client.write("secret/endpoint/django", secret_key = str(uuid.uuid4()))
    db = {
        "name": db_name,
        "user": username,
        "password": password,
        "port": port
    }
    client.write("secret/endpoint/django/db", **db)
        
def _vault_django(machine = None):
    args = []
    for key in ["name", "user", "password", "port"]:
        args.append(input(key + ": "))
        
    vault_django(*args, machine = machine)
        
COMMANDS = {
    "vault-init": vault_init,
    "vault-configure": vault_configure,
    "vault-unseal": vault_unseal,
    "vault-seal": vault_seal,
    "vault-status": vault_status,
    "vault-provision": _vault_provision,
    "vault-revoke": _vault_revoke,
    "vault-django": _vault_django,
    "verify":verify,
}

if __name__ == '__main__':
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
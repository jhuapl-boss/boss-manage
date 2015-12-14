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

"""Location to store and read the Vault's Root Token"""
VAULT_TOKEN = "private/vault_token"
VAULT_KEY = "private/vault_key."
NEW_TOKEN = "private/new_token"

def get_client(read_token = False):
    """Open a connection to the Vault located at http://localhost:8200
    
    If read_token == True then read the token from VAULT_TOKEN and verify
    that the client is authenticated to the Vault.
    
    Exits (sys.exit) if read_token and VAULT_TOKEN does not exists
    Exits (sys.exit) if read_token and VAULT_TOKEN does not contain a valid
                     token
    """
    client = hvac.Client(url="http://localhost:8200")
    
    if read_token:
        if not os.path.exists(VAULT_TOKEN):
            print("Need the root token to communicate with the Vault, exiting...")
            sys.exit(1)
            
        with open(VAULT_TOKEN, "r") as fh:
            client.token = fh.read()
            if not client.is_authenticated():
                print("Vault token is not valid, cannot communicate with the Vault, exiting...")
                sys.exit(1)
            
    return client

def vault_init():
    """Initialize a Vault. Connect using get_client() and if the Vault is not
    initialized then initialize it with 5 secrets and a threashold of 3. The
    keys are stored as VAULT_KEY and root token is stored as VAULT_TOKEN.
    
    After initializing the Vault it is unsealed for use.
    """
       
    client = get_client()
    if client.is_initialized():
        print("Vault is already initialized")
        return
    
    secrets = 5
    threashold = 3
    print("Initializing with {} secrets and {} needed to unseal".format(secrets, threashold))
    result = client.initialize(secrets, threashold)
    
    with open(VAULT_TOKEN, "w") as fh:
        fh.write(result["root_token"])
    for i in range(secrets):
        with open(VAULT_KEY + str(i+1), "w") as fh:
            fh.write(result["keys"][i])
       
    print()
    print("======== WARNING WARNING WARNING ========")
    print("= Vault root token and unseal keys were =")
    print("= written to disk. PROTECT these files. =")
    print("======== WARNING WARNING WARNING ========")
    
    print()
    print("Unsealing Vault")
    client.unseal_multi(result["keys"])
    
def vault_unseal():
    """Unseal a sealed Vault. Connect using get_client() and if the Vault is
    not sealed read all of the keys defined by VAULT_KEY and unseal.
    
    If there are not enough keys to completely unseal the Vault, print a
    status message about how many more keys are required to finish the
    process.
    """
    
    client = get_client()
    if not client.is_sealed():
        print("Vault is already unsealed")
        return
        
    keys = []
    for f in glob.glob(VAULT_KEY + "*"):
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
        
def vault_seal():
    """Seal an unsealed Vault. Connect using get_client(True) and if the Vault
    is unsealed, seal it.
    
    Used to quickly protect a Vault without having to stop the Vault service
    on a protected VM.
    """
    
    client = get_client(read_token = True)
    if client.is_sealed():
        print("Vault is already sealed")
        return

    client.seal()
    print("Vault is sealed")
    
def vault_status():
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
    
    client = get_client(read_token = True)
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
    
def vault_provision():
    """Create a new Vault access token. Connect using get_client(True),
    request a new access token (default policy), and save it to NEW_TOKEN.
    """
    client = get_client(read_token = True)
    
    token = client.create_token()
    with open(NEW_TOKEN, "w") as fh:
        fh.write(token["auth"]["client_token"])

def vault_revoke():
    """Revoke a Vault access token. Connect using get_client(True), read the
    token (using input()), and then revoke the token.
    """
    client = get_client(read_token = True)
    token = input("token: ")
    
    client.revoke_token(token)
        
def vault_django():
    """Provision a Vault with credentials for a Django webserver. Connect
    using get_client(True) and provision the following information:
     * Generate a secret key and store under 'secret/django secret_key=`
     * Prompt the user (using input()) for the
       - Database Name
       - Database Username
       - Database Password
       - Database Hostname
       - Database Port
       and store under
       - 'secret/django/db name='
       - 'secret/django/db user='
       - 'secret/django/db password='
       - 'secret/django/db host='
       - 'secret/django/db port='
    """
    client = get_client(read_token = True)
    
    client.write("secret/django", secret_key = str(uuid.uuid4()))
    db = {}
    for key in ["name", "user", "password", "host", "port"]:
        db[key] = input(key + ": ")
    client.write("secret/django/db", **db)
        
COMMANDS = {
    "vault-init": vault_init,
    "vault-unseal": vault_unseal,
    "vault-seal": vault_seal,
    "vault-status": vault_status,
    "vault-provision": vault_provision,
    "vault-revoke": vault_revoke,
    "vault-django": vault_django,
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
    parser.add_argument("command",
                        choices = commands,
                        metavar = "command",
                        help = "Command to execute")

    args = parser.parse_args()

    if args.command in COMMANDS:
        COMMANDS[args.command]()
    else:
        parser.print_usage()
        sys.exit(1)
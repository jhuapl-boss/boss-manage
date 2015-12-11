#!/usr/bin/env python3

import sys
import os
import glob
import hvac
import json
import uuid

VAULT_TOKEN = "private/vault_token"
VAULT_KEY = "private/vault_key."
NEW_TOKEN = "private/new_token"

def get_client(read_token = False):
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
    """Initialize the Vault, store the unseal keys and root token.
       Finish by unsealing the new vault."""
       
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
    """Used to reopen an initialized vault using previously saved values"""
    
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
    """ Used to quickly reseal a vault if there is any need"""
    
    client = get_client(read_token = True)
    if client.is_sealed():
        print("Vault is already sealed")
        return

    client.seal()
    print("Vault is sealed")
    
def vault_status():
    """ Print the current status of the Vault """
    
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
    client = get_client(read_token = True)
    
    token = client.create_token()
    with open(NEW_TOKEN, "w") as fh:
        fh.write(token["auth"]["client_token"])

def vault_revoke():
    client = get_client(read_token = True)
    token = input("token: ")
    
    client.revoke_token(token)
        
def vault_django():
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

def usage():
    vault_keys = "|".join(COMMANDS.keys())
    print("Usage: {} ({})".format(sys.argv[0], vault_keys))
    sys.exit(1)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        usage()

    cmd = sys.argv[1]
    
    if cmd in COMMANDS:
        COMMANDS[cmd]()
    else:
        usage()
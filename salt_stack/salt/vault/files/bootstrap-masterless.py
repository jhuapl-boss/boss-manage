#!/usr/bin/env python3

import sys
import os
import socket
import hvac
import uuid

VAULT_PROTOCOL = "http"
VAULT_PORT = 8200
VAULT_MASTER = "vault-master"
VAULT_STORE = "/root/"

def f(*args):
    a = os.path.join(*args)
    return os.path.join(VAULT_STORE, a)

def have_dns(name):
    try:
        socket.getaddrinfo(name, VAULT_PORT)
        return True
    except socket.gaierror:
        return False

def hostname():
    return socket.gethostname().lower()
    
def are_master():
    return have_dns(VAULT_MASTER) and hostname() == VAULT_MASTER
    
def connect():
    url = "%s://%s:%d" % (VAULT_PROTOCOL, VAULT_MASTER, VAULT_PORT)
    return hvac.Client(url=url)
    
def initialize(c, secrets, threashold):
    """Initialize the Vault, store the unseal keys and root token.
       Finish by unsealing the new vault."""
    
    result = c.initialize(secrets, threashold)
    c.token = result["root_token"]
    
    with open(f("vault_token"), "w") as fh:
        fh.write(result["root_token"])
    for i in range(secrets):
        with open(f("vault_key." + str(i+1)), "w") as fh:
            fh.write(result["keys"][i])
            
    print "======== WARNING WARNING WARNING ========"
    print "= Vault root token and unseal keys were ="
    print "= written to disk. PROTECT these files. ="
    print "  ", VAULT_STORE
    print "======== WARNING WARNING WARNING ========"
    
    c.unseal_multi(result["keys"])
    
def unseal(c):
    """Used to reopen an initialized vault using previously saved values"""
    keys = []
    import glob
    for f in glob.glob(f("vault_key.*")):
        with open(f, "r") as fh:
            keys.append(fh.read())
    
    c.unseal_multi(keys)
    
    
def configure_audit(c):
    c.enable_audit_backend("file", options={"path": "/var/log/vault_audit.log"})
    
def configure_acl(c):
    with open("provisioner.hcl", "r") as fh:
        c.set_policy("provisioner", fh.read())
    with open("vault.hcl", "r") as fh:
        c.set_policy("vault", fh.read())
    
def configure_aws(c):
    c.enable_secret_backend("aws")
    c.write("aws/config/root",
            access_key="",
            secret_key="",
            region="us-east-1")
    
def configure_pki(c):
    c.enable_secret_backend("pki")
    c.write("pki/config/ca",
            pem_bundle="")
    c.write("pki/roles/microns-dot-com",
            allowed_base_domain="microns.com",
            allow_subdomains="true",
            max_ttl="72h")

def configure_app(c):
    c.enable_auth_backend("app-id")
    c.write("auth/app-id/map/app-id/vault",
            value="vault",
            display_name="vault")
    
def create_provisioner(c):
    token = c.create_token(policies=["provisioner"])
    with open(f("provisioner_token"), "w") as fh:
        fh.write(token["auth"]["client_token"])

if __name__ == "__main__":
    if not are_master():
        print "Not %s, cannot bootstrap" % VAULT_MASTER
        sys.exit(1)
        
    c = connect()
    if not c.is_initialized():
        initialize(c, 5, 3)
        configure_audit(c)
        configure_acl(c)
        #configure_aws(c)
        #configure_pki(c)
        configure_app(c)
        create_provisioner(c)
    elif c.is_sealed():
        unseal(c)
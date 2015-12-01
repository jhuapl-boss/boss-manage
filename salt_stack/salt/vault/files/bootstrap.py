#!/usr/bin/env python3

import sys
import os
import socket
import hvac

VAULT_PROTOCOL = "http"
VAULT_PORT = 8200
VAULT_SERVER = "vault"
VAULT_MASTER = "vault-master"
VAULT_STORE = "/root/"
VAULT_USER_ID = "vault_user"

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

def have_master():
    return has_dns(VAULT_MASTER)
    
def are_client():
    return have_dns(VAULT_SERVER) and hostname() == VAULT_SERVER
    
def gen_url(host):
    return "%s://%s:%d" % (VAULT_PROTOCOL, host, VAULT_PORT)
    
def master_client(user_id):
    m = hvac.Client(url=gen_url(VAULT_MASTER))
    m.auth_app_id("vault", user_id) # how do we want to authenticate
    if not m.is_authenticated():
        raise Exception("Cannot authenticate to " + VAULT_MASTER)
    return m
    
def local_client():
    return hvac.Client(url=gen_url(VAULT_SERVER))
    
def initialize(c, m, secrets, threashold):
    """Initialize the Vault, store the unseal keys and root token.
       Finish by unsealing the new vault."""

    result = c.initialize(secrets, threashold)
    c.token = results["root_token"]
    
    m.write("secret/%s" % (hostname(), ),
            root_token = result["root_token"])
            
    keys = {}
    for i in range(secrets):
        keys["key" + str(i+1)] = result["keys"][i]
    # Store in a cubbyhole to limit access to the keys
    # Stores as subbyhole/keys key1=xxx key2=yyy ...
    m.write("cubbyhole/keys",
            **keys)
    
    c.unseal_multi(result["keys"])
    
def unseal(c, m):
    keys = m.read("cubbyhole/keys")["data"].values()
    
    c.unseal_multi(keys)
    
def configure_audit(c):
    c.enable_audit_backend("file", options={"path": "/var/log/vault_audit.log"})
    
def configure_acl(c):
    c.set_policy("", "")
    
def configure_aws(c, m):
    c.enable_secret_backend("aws")
    c.write("aws/config/root",
            access_key="",
            secret_key="",
            region="us-east-1")
    
def configure_pki(c, m):
    c.enable_secret_backend("pki")
    c.write("pki/config/ca",
            pem_bundle="")
    c.write("pki/roles/microns-dot-com",
            allowed_base_domain="microns.com",
            allow_subdomains="true",
            max_ttl="72h")

def configure_app(c):
    c.enable_auth_backend("app-id")
    c.write("auth/app-id/map/app-id/test")

if __name__ == "__main__":
    if not are_client():
        print "Not a vault, cannot bootstrap"
        sys.exit(1)
    
    user_id = f(VAULT_USER_ID)
    if not os.path.exists(user_id):
        print "User ID file '%s' does not exist, cannot initialize nor unseal Vault" % VAULT_USER_ID
        sys.exit(1)
        
    with open(user_id, "r") as fh:
        user_id = fh.read()
    
    m = master_client(user_id)
    c = local_client()
    if not c.is_initialized():
        initialize(c, m, 1, 1)
        configure_audit(c)
        #configure_acl(c)
        #configure_aws(c,m)
        #configure_pki(c,m)
        #configure_app(c)
    elif c.is_sealed():
        unseal(c, m)
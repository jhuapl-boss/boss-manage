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

def gen_url():
    return "%s://%s:%d" % (VAULT_PROTOCOL, VAULT_MASTER, VAULT_PORT)

def provision(who):
    with open(f("provisioner_token"), "r") as fh:
        token = fh.read()
        
    c = hvac.Client(url=gen_url(), token=token)

    if not c.is_authenticated():
        raise Exception("Cannot authenticate to %s" % VAULT_MASTER)
    
    user_id = uuid.uuid4() # random uuid
    user_id = user_id.hex[-6:] # make it easy to type
    
    c.write("auth/app-id/map/user-id/%s" % (user_id, ),
            value="vault")
            
    file = f("%s_user" % who)
    with open(file, "w") as fh:
        fh.write(user_id)
        
    print "User Id written to '%s'" % file

if __name__ == "__main__":
    if not are_master():
        print "Not vault-master, cannot bootstrap"
        #sys.exit(1)
        
    action = None
    if len(sys.argv) > 1:
        action = sys.argv[1]
        
    if action in ("provision", ):
        provision(sys.argv[2])
    else:
        print "Usage: %s provision <who>" % sys.argv[0]
        sys.exit(1)
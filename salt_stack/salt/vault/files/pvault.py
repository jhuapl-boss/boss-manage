#!/usr/bin/env python3

import sys
import getpass
import socket
from subprocess import Popen, PIPE
import hvac

VAULT_PROTOCOL = "http"
VAULT_PORT = 8200
VAULT_SERVER = "vault"
VAULT_APP = "test"
VAULT_USER = "test"

def vault_client():
    url = "%s://%s:%s" % (VAULT_PROTOCOL, VAULT_SERVER, VAULT_PORT)
    client = hvac.Client(url=url)
    client.auth_app_id(VAULT_APP, VAULT_USER)
    if not client.is_authenticated():
        raise Exception("Could not connect to vault")
    return client
    
def hostname():
    return socket.gethostname().lower()

def gen_password():
    return "42"

def update_password(user):
    password = gen_password()
    
    # sudo is set to not require password
    p = Popen(["sudo", "-S", "chpasswd", stdin=PIPE])
    p.communicate("%s:%s" % (user, password))
    
    # secret/<hostname>/user/<username> password=*****
    bucket = "secret/%s/user/%s" % (hostname(),user)
    
    c = vault_client()
    c.write(bucket, password=password)
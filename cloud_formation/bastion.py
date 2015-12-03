#!/usr/bin/env python3

import subprocess
import shlex
import os
import signal
import sys
import time
from boto3.session import Session
import json
import hvac


def become_tty_fg():
    """ From: http://stackoverflow.com/questions/15200700/how-do-i-set-the-terminal-foreground-process-group-for-a-process-im-running-und
        Create a new foreground process group for the new process
    """
    os.setpgrp()
    hdlr = signal.signal(signal.SIGTTOU, signal.SIG_IGN)
    tty = os.open('/dev/tty', os.O_RDWR)
    os.tcsetpgrp(tty, os.getpgrp())
    signal.signal(signal.SIGTTOU, hdlr)

def ssh(key, remote, bastion):
    fwd_cmd = "ssh -i {} -N -L 2222:{}:22 ec2-user@{}".format(key, remote, bastion)
    ssh_cmd = "ssh -i {} -p 2222 ubuntu@localhost".format(key)
    
    proc = subprocess.Popen(shlex.split(fwd_cmd))
    time.sleep(1) # wait for the tunnel to be setup
    try:
        ret = subprocess.call(shlex.split(ssh_cmd), close_fds=True, preexec_fn=become_tty_fg)
    finally:
        proc.terminate()
        proc.wait()
    
def connect_vault(key, remote, bastion, cmd):
    fwd_cmd = "ssh -i {} -N -L 8200:{}:8200 ec2-user@{}".format(key, remote, bastion)

    proc = subprocess.Popen(shlex.split(fwd_cmd))
    time.sleep(1) # wait for the tunnel to be setup
    try:
        client = hvac.Client(url="http://localhost:8200")
        cmd(client)
    finally:
        proc.terminate()
        proc.wait()
        
def vault_init(client):
    """Initialize the Vault, store the unseal keys and root token.
       Finish by unsealing the new vault."""
       
    if client.is_initialized():
        print("Vault is already initialized")
        return
    
    secrets = 5
    threashold = 3
    print("Initializing with {} secrets and {} needed to unseal".format(secrets, threashold))
    result = client.initialize(secrets, threashold)
    
    with open("vault_token", "w") as fh:
        fh.write(result["root_token"])
    for i in range(secrets):
        with open("vault_key." + str(i+1), "w") as fh:
            fh.write(result["keys"][i])
       
    print()
    print("======== WARNING WARNING WARNING ========")
    print("= Vault root token and unseal keys were =")
    print("= written to disk. PROTECT these files. =")
    print("======== WARNING WARNING WARNING ========")
    
    print()
    print("Unsealing Vault")
    client.unseal_multi(result["keys"])
    
def vault_unseal(client):
    """Used to reopen an initialized vault using previously saved values"""
    
    if not client.is_sealed():
        print("Vault is already unsealed")
        return
        
    keys = []
    import glob
    for f in glob.glob("vault_key.*"):
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
        
def vault_seal(client):
    """ Used to quickly reseal a vault if there is any need"""
    
    if client.is_sealed():
        print("Vault is already sealed")
        return
    
    if not os.path.exists("vault_token"):
        print("Need the root token to seal the vault")
        return
        
    with open("vault_token", "r") as fh:
        client.token = fh.read()
        if not client.is_authenticated():
            print("Vault token is not valid, cannot seal vault")
            return

    client.seal()
    print("Vault is sealed")
    
def vault_status(client):
    """ Print the current status of the Vault """
    
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
    
    if not os.path.exists("vault_token"):
        print("Need the root token to communicate with the Vault")
        return
        
    with open("vault_token", "r") as fh:
        client.token = fh.read()
        if not client.is_authenticated():
            print("Vault token is not valid, cannot communicate with the Vault")
            return
      
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

def create_session(cred_file):
    with open(cred_file, "r") as fh:
        credentials = json.load(fh)
        
    session = Session(aws_access_key_id = credentials["aws_access_key"],
                      aws_secret_access_key = credentials["aws_secret_key"],
                      region_name = 'us-east-1')
    return session
    
def machine_lookup(session, hostname):
    client = session.client('ec2')
    response = client.describe_instances(Filters=[{"Name":"tag:Name", "Values":[hostname]},
                                                  {"Name":"instance-state-name", "Values":["running"]}])\

    item = response['Reservations']
    if len(item) == 0:
        return None
    else:
        item = item[0]['Instances']
        if len(item) == 0:
            return None
        else:
            item = item[0]
            if 'PublicIpAddress' in item:
                return item['PublicIpAddress']
            elif 'PrivateIpAddress' in item:
                return item['PrivateIpAddress']
            else:
                return None
    
def usage():
    print("Usage: {} <aws-credentials> <ssh_key> <bastion_hostname> <internal_hostname> (ssh|vault-init|vault-unseal|vault-seal|vault-status)".format(sys.argv[0]))
    sys.exit(1)
    
if __name__ == "__main__":
    if len(sys.argv) < 6:
        usage()
    
    cred_file = sys.argv[1]
    key = sys.argv[2]
    bastion = sys.argv[3]
    private = sys.argv[4]
    cmd = sys.argv[5]
    
    session = create_session(cred_file)
    bastion = machine_lookup(session, bastion)
    private = machine_lookup(session, private)
    
    if cmd in ("ssh",):
        ssh(key, private, bastion)
    elif cmd in ("vault-init",):
        connect_vault(key, private, bastion, vault_init)
    elif cmd in ("vault-unseal",):
        connect_vault(key, private, bastion, vault_unseal)
    elif cmd in ("vault-seal",):
        connect_vault(key, private, bastion, vault_seal)
    elif cmd in ("vault-status",):
        connect_vault(key, private, bastion, vault_status)
    else:
        usage()
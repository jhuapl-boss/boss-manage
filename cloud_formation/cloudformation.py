#!/usr/bin/env python3

import sys
import importlib
from boto3.session import Session
import json
import pprint

import hosts

"""
create vpc.boss vpc
create subnet.vpc.boss subnet
create subnet.vpc.boss instance
"""

def create_session(credentials):
    session = Session(aws_access_key_id = credentials["aws_access_key"],
                      aws_secret_access_key = credentials["aws_secret_key"],
                      region_name = 'us-east-1')
    return session
    
def create_config(session, domain, config):
    module = importlib.import_module("configs." + config)
    module.create(session, domain)
    
def generate_config(domain, config):
    module = importlib.import_module("configs." + config)
    module.generate("templates", domain)

def usage():
    print("Usage: {} <aws-credentials> (create|generate) <domain_name> <config_name>".format(sys.argv[0]))
    sys.exit(1)

if __name__ == '__main__':
    if len(sys.argv) < 5:
        usage()
        
    cred_file = sys.argv[1]
    action = sys.argv[2]
    domain_name = sys.argv[3]
    config_name = sys.argv[4]
    
    with open(cred_file, "r") as fh:
        credentials = json.load(fh)
    
    session = create_session(credentials)

    if action in ("create", ):
        create_config(session, domain_name, config_name)
    elif action in ("generate", "gen"):
        generate_config(domain_name, config_name)
    else:
        usage()
    
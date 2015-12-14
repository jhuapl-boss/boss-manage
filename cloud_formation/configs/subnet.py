"""Create a Subnet.

DEVICES - the different device configurations to include in the template.
"""

import pprint
import json
import os
import library as lib
import hosts

DEVICES = ["subnet"]

def verify_domain(domain):
    """Verify that the given domain is valid in the format 'subnet.vpc.tld'."""
    if len(domain.split(".")) != 3:
        raise Exception("Not a valiid Subnet domain name")

def generate(folder, domain):
    """Generate the CloudFormation template and save to disk."""
    verify_domain(domain)
    
    parameters, resources = lib.load_devices(*DEVICES)
    template = lib.create_template(parameters, resources)
    
    lib.save_template(template, folder, domain)

def create(session, domain):
    """Verify that the referenced VPC already exist and that the referenced
    Subnet does not already exist. Then create the CloudFormation stack.
    """
    verify_domain(domain)

    vpc_domain = domain.split(".", 1)[1]
    vpc_id = lib.vpc_id_lookup(session, vpc_domain)
    if vpc_id is None:
        raise Exception("VPC does not exists")
        
    subnet_id = lib.subnet_id_lookup(session, domain)
    if subnet_id is not None:
        raise Exception("Subnet already exists")
        
    subnet_net = hosts.lookup(domain)
    
    args = [
        lib.template_argument("VPCId", vpc_id),
        lib.template_argument("Domain", domain),
        lib.template_argument("IPSubnet", subnet_net)
    ]
    
    parameters, resources = lib.load_devices(*DEVICES)
    template = lib.create_template(parameters, resources)
    stack_name = lib.domain_to_stackname(domain)
    
    lib.cloudformation_create(session, stack_name, template, args)
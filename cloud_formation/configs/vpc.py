import pprint
import json
import os
import library as lib
import hosts

DEVICES = ["vpc"]

def verify_domain(domain):
    if len(domain.split(".")) != 2: # vpc.tld
        raise Exception("Not a valiid VPC domain name")

def generate(folder, domain):
    verify_domain(domain)
    
    parameters, resources = lib.load_devices(*DEVICES)
    template = lib.create_template(parameters, resources)
    
    lib.save_template(template, folder, domain)

def create(session, domain):
    verify_domain(domain)

    vpc_id = lib.vpc_id_lookup(session, domain)
    if vpc_id is not None:
        raise Exception("VPC already exists")

    vpc_net = hosts.lookup(domain)
    
    args = [
        lib.template_argument("Domain", domain),
        lib.template_argument("IPSubnet", vpc_net)
    ]
    
    parameters, resources = lib.load_devices(*DEVICES)
    template = lib.create_template(parameters, resources)
    stack_name = lib.domain_to_stackname(domain)
    
    client = session.client('cloudformation')
    response = client.create_stack(
        StackName = stack_name,
        TemplateBody = template,
        Parameters = args
    )
    pprint.pprint(response)
"""Create a VPC and update the default route table and security group.

DEVICES - the different device configurations to include in the template.
"""

import pprint
import json
import os
import library as lib
import hosts

DEVICES = ["vpc"]

def verify_domain(domain):
    """Verify that the given domain is valid in the format 'vpc.tld'."""
    if len(domain.split(".")) != 2:
        raise Exception("Not a valiid VPC domain name")

def generate(folder, domain):
    """Generate the CloudFormation template and save to disk."""
    verify_domain(domain)
    
    parameters, resources = lib.load_devices(*DEVICES)
    template = lib.create_template(parameters, resources)
    
    lib.save_template(template, folder, domain)
    
def set_default_route_table_name(session, domain):
    """Set the name of the default route table for the VPC to 'internal'."""
    vpc_id = lib.vpc_id_lookup(session, domain)
    
    client = session.client('ec2')
    response = client.describe_route_tables(Filters=[{"Name":"vpc-id", "Values":[vpc_id]}])
    rt_id = response['RouteTables'][0]['RouteTableId']
    
    resource = session.resource('ec2')
    rt = resource.RouteTable(rt_id)
    response = rt.create_tags(Tags=[{"Key": "Name", "Value": "internal"}])
    
def update_sg(session, domain):
    """Add a new route for all protocols to 10.0.0.0/8 to the default
    security group fr the VPC.
    """
    vpc_id = lib.vpc_id_lookup(session, domain)
    
    sg_id = lib.sg_lookup(session, vpc_id, "default")
    
    resource = session.resource('ec2')
    sg = resource.SecurityGroup(sg_id)
    
    sg.authorize_ingress(IpProtocol="-1", CidrIp='10.0.0.0/8')
    

def create(session, domain):
    """Verify that the VPC does not already exist and then create the
    CloudFormation stack and then update the default route table and
    security group.
    """
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
    
    lib.cloudformation_create(session, stack_name, template, args)
    
    set_default_route_table_name(session, domain)
    update_sg(session, domain)
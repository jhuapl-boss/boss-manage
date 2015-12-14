"""Create the public parts of the core environment.

DEVICES - the different device configurations to include in the template.
"""

import library as lib
import hosts
import pprint

DEVICES = ["inet_gw", "bastion"]

def verify_domain(domain):
    """Verify that the given domain is valid in the format 'subnet.vpc.tld'."""
    if len(domain.split(".")) != 3: # subnet.vpc.tld
        raise Exception("Not a valiid Subnet domain name")

def generate(folder, domain):
    """Generate the CloudFormation template and save to disk."""
    verify_domain(domain)
    
    parameters, resources = lib.load_devices(*DEVICES)
    template = lib.create_template(parameters, resources)
    
    lib.save_template(template, folder, "core." + domain)

def create(session, domain):
    """Lookup all of the needed arguments, and create the CloudFormation
    stack.
    """
    verify_domain(domain)
    
    vpc_domain = domain.split(".", 1)[1]
    vpc_id = lib.vpc_id_lookup(session, vpc_domain)
    if vpc_id is None:
        raise Exception("VPC does not exists")

    subnet_id = lib.subnet_id_lookup(session, domain)
    if subnet_id is None:
        raise Exception("Subnet doesn't exists")
        
    keypair = lib.keypair_lookup(session)
    default_sg_id = lib.sg_lookup(session, vpc_id, "default")
    
    args = [
        lib.template_argument("KeyName", keypair),
        lib.template_argument("VPCId", vpc_id),
        lib.template_argument("SubnetId", subnet_id),
        lib.template_argument("DefaultSecurityGroup", default_sg_id),
        lib.template_argument("BastionAMI", lib.ami_lookup(session, "amzn-ami-vpc-nat-hvm-2015.03.0.x86_64-ebs")),
        lib.template_argument("BastionHostname", "bastion.core.boss"),
        lib.template_argument("BastionIP", hosts.lookup("bastion.core.boss")),
    ]
    
    parameters, resources = lib.load_devices(*DEVICES)
    template = lib.create_template(parameters, resources)
    stack_name = lib.domain_to_stackname("core." + domain)
    
    lib.cloudformation_create(session, stack_name, template, args)
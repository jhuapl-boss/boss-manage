import library as lib
import hosts
import pprint

DEVICES = ["inet_gw", "bastion"]

def verify_domain(domain):
    if len(domain.split(".")) != 3: # subnet.vpc.tld
        raise Exception("Not a valiid Subnet domain name")

def generate(folder, domain):
    verify_domain(domain)
    
    parameters, resources = lib.load_devices(*DEVICES)
    template = lib.create_template(parameters, resources)
    
    lib.save_template(template, folder, "core." + domain)

def create(session, domain):
    verify_domain(domain)
    
    vpc_domain = domain.split(".", 1)[1]
    vpc_id = lib.vpc_id_lookup(session, vpc_domain)
    if vpc_id is None:
        raise Exception("VPC does not exists")

    subnet_id = lib.subnet_id_lookup(session, domain)
    if subnet_id is None:
        raise Exception("Subnet doesn't exists")
    
    args = [
        lib.template_argument("VPCId", vpc_id),
        lib.template_argument("SubnetId", subnet_id),
        lib.template_argument("BastionAMI", lib.ami_lookup(session, "amzn-ami-vpc-nat-hvm-2015.03.0.x86_64-ebs")),
        lib.template_argument("BastionHostname", "bastion.core.boss"),
        lib.template_argument("BastionIP", hosts.lookup("bastion.core.boss")),
    ]
    
    parameters, resources = lib.load_devices(*DEVICES)
    template = lib.create_template(parameters, resources)
    stack_name = lib.domain_to_stackname("core." + domain)
    
    client = session.client('cloudformation')
    response = client.create_stack(
        StackName = stack_name,
        TemplateBody = template,
        Parameters = args
    )
    pprint.pprint(response)
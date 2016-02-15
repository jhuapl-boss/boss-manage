"""
Create the load balancer on top of a production stack.The load balancer stack consists of
  * A Load Balancer
  * If production it uses the certificate key associated with api.theboss.io

The load balancer currently assumes a single endpoint named with the naming standards of
a production configuration.  It also expects for the user to select the same KeyPair
used when creating the core configuration.

ADDRESSES - the dictionary of production hostnames and subnet indexes.
"""


import configuration
import library as lib
import hosts
import pprint


def create_config(session, domain, keypair=None, user_data=None, db_config={}):
    """Create the CloudFormationConfiguration object."""
    config = configuration.CloudFormationConfiguration(domain)

    # do a couple of verification checks
    if config.subnet_domain is not None:
        raise Exception("Invalid VPC domain name")

    vpc_id = lib.vpc_id_lookup(session, domain)
    if session is not None and vpc_id is None:
        raise Exception("VPC does not exists, exiting...")

    # Lookup the VPC, External Subnet, that are needed by other resources
    config.add_arg(configuration.Arg.VPC("VPC", vpc_id,
                                         "ID of VPC to create resources in"))

    external_subnet_id = lib.subnet_id_lookup(session, "external." + domain)
    config.add_arg(configuration.Arg.Subnet("ExternalSubnet",
                                            external_subnet_id,
                                            "ID of External Subnet to create resources in"))

    client = session.client('ec2')
    response = client.describe_instances()
    #Filters=[{'Name':'string','Values': [] }]
    print(response)

    # # Create New HTTPS Security Group and LoadBalancer
    # config.add_security_group("AllHTTPSSecurityGroup",
    #                           "http",
    #                           [("tcp", "443", "443", "0.0.0.0/0")])
    #
    # loadbalancer_name = "elb-" + domain.replace(".", "-")  #elb names can't have periods in them.
    # config.add_loadbalancer("LoadBalancer",
    #                         loadbalancer_name,
    #                         ["Endpoint"],
    #                         subnets = ["ExternalSubnet"],
    #                         security_groups=["AllHTTPSSecurityGroup"],
    #                         depends_on = ["Endpoint", "AllHTTPSecurityGroup"])

    return config

def generate(folder, domain):
    """Create the configuration and save it to disk"""
    name = lib.domain_to_stackname("core." + domain)
    config = create_config(None, domain)
    config.generate(name, folder)

def create(session, domain):
    """Create the configuration, launch it, and initialize Vault"""
    name = lib.domain_to_stackname("core." + domain)
    config = create_config(session, domain)

    # success = config.create(session, name)
    # if success:
    #     vpc_id = lib.vpc_id_lookup(session, domain)
    #     lib.rt_name_default(session, vpc_id, "internal." + domain)
    #
    #     try:
    #         print("Waiting 2.5 minutes for VMs to start...")
    #         time.sleep(150)
    #         print("Initializing Vault...")
    #         lib.call_vault(session,
    #                        lib.keypair_to_file(keypair),
    #                        "bastion." + domain,
    #                        "vault." + domain,
    #                        "vault-init")
    #     except requests.exceptions.ConnectionError:
    #         print("Could not connect to Vault, manually initialize it before launching other machines")

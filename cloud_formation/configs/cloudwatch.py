"""
Create the cloudwatch alarms for the load balancer on top of a loadbalancer stack.The cloudwatch stack consists of
  * alarms monitor traffic in and out of the load balancer

"""


import configuration
import library as lib


def create_config(session, domain, keypair=None, user_data=None, db_config={}):
    """Create the CloudFormationConfiguration object.
    :arg session used to perform lookups
    :arg domain DNS name of vpc
    :arg keypair AWS keypair used to instantiate
    :arg user_data custom data needed for config
    :arg db_config database config
    """
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



    loadbalancer_name = "elb-" + domain.replace(".", "-")  # elb names can't have periods in them.
    is_lb = lib.lb_lookup(session, loadbalancer_name)
    if not is_lb:
        raise Exception("Invalid load balancer name: " + loadbalancer_name)

    config.add_cloudwatch( loadbalancer_name,
                           "arn:aws:sns:us-east-1:256215146792:ProductionMicronsMailingList")
    return config


def generate(folder, domain):
    """Create the configuration and save it to disk
    :arg folder location to generate the cloudformation template stack
    :arg domain internal DNS name"""
    name = lib.domain_to_stackname("loadbalancer." + domain)
    config = create_config(None, domain)
    config.generate(name, folder)


def create(session, domain):
    """Create the configuration, launch it, and initialize Vault
    :arg session information for performing lookups
    :arg domain internal DNS name """
    name = lib.domain_to_stackname("cloudwatch." + domain)
    config = create_config(session, domain)

    success = config.create(session, name)

    if success:
        print('success')
    else:
        print('failed')

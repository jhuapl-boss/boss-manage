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
    """
    Create the CloudFormationConfiguration object.
    Args:
        session: aws session key
        domain: domain used to create this system
        keypair: aws keypair used to create resources
        user_data: Not used in this but is used in other config files, needed for compatibility
        db_config: Not used in this but is used in other config files, needed for compatibility

    Returns: aws cloudformation stack

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

    external_subnet_id = lib.subnet_id_lookup(session, "external." + domain)
    config.add_arg(configuration.Arg.Subnet("ExternalSubnet",
                                            external_subnet_id,
                                            "ID of External Subnet to create resources in"))

    endpoint_instance_id = lib.instanceid_lookup(session, "endpoint."+domain)
    if endpoint_instance_id is None:
        raise Exception("Invalid instance name: endpoint.external."+domain)
    config.add_arg(configuration.Arg.Instance("Endpoint",
                                              endpoint_instance_id,
                                              "ID of the Endpoint Instance to attach the LoadBalancer"))

    # Create New HTTPS Security Group and LoadBalancer
    config.add_security_group("AllHTTPSSecurityGroup",
                              "http",
                              [("tcp", "443", "443", "0.0.0.0/0")])

    listeners = []
    # cert="arn:aws:acm:us-east-1:256215146792:certificate/afb78241-a392-43e1-9317-f42ffafc432f"
    cert = lib.cert_arn_lookup(session, "api.theboss.io")
    listeners.append(lib.create_elb_listener("443","80","HTTPS", cert ))

    loadbalancer_name = "elb." + domain
    config.add_loadbalancer("LoadBalancer",
                            loadbalancer_name,
                            listeners,
                            ["Endpoint"],
                            subnets=["ExternalSubnet"],
                            security_groups=["AllHTTPSSecurityGroup"],
                            depends_on = ["AllHTTPSSecurityGroup"])

    return config


def generate(folder, domain):
    """Create the configuration and save it to disk"""
    name = lib.domain_to_stackname("loadbalancer." + domain)
    config = create_config(None, domain)
    config.generate(name, folder)


def create(session, domain):
    """Create the configuration, launch it, and initialize Vault"""
    name = lib.domain_to_stackname("loadbalancer." + domain)
    config = create_config(session, domain)

    success = config.create(session, name)

    if success:
        print('success')

        print("KeyPair to communicating with Vault")
        keypair = lib.keypair_lookup(session)
        call = lib.ExternalCalls(session, keypair, domain)

        def configure_auth(auth_port):
            dns = lib.elb_public_lookup(session, "elb." + domain)
            uri = "https://{}".format(dns)
            call.vault_update("secret/endpoint/auth", public_uri = uri)

            creds = call.vault_read("secret/auth")
            kc = lib.KeyCloakClient("http://localhost:{}".format(auth_port))
            kc.login(creds["username"], creds["password"])
            kc.add_redirect_uri("BOSS","endpoint", uri + "/*")
            kc.logout()
        call.set_ssh_target("auth")
        call.ssh_tunnel(configure_auth, 8080)

        print("Restart Django on the Endpoint Servers")
    else:
        print('failed')
"""
Create the core configuration which consists of
  * A new VPC
  * An internal subnet containing a Vault server
  * An external subnet containing a Bastion server

The core configuration create all of the infrastructure that is required for
the other production resources to function. In the furture this may include
other servers for services like Authentication.
"""

import library as lib
import configuration
import hosts
import time
import requests
import scalyr

import os
import json

keypair = None

# Region core is created in.  Later versions of boto3 should allow us to
# extract this from the session variable.  Hard coding for now.
CORE_REGION = 'us-east-1'

INCOMING_SUBNET = "52.3.13.189/32" # microns-bastion elastic IP


def create_config(session, domain):
    """Create the CloudFormationConfiguration object."""
    config = configuration.CloudFormationConfiguration(domain, CORE_REGION)

    if config.subnet_domain is not None:
        raise Exception("Invalid VPC domain name")

    vpc_id = lib.vpc_id_lookup(session, domain)
    if session is not None and vpc_id is None:
        raise Exception("VPC does not exists, exiting...")

    global keypair
    keypair = lib.keypair_lookup(session)

    config.add_arg(configuration.Arg.VPC("VPC", vpc_id,
                                         "ID of VPC to create resources in"))

    internal_subnet_id = lib.subnet_id_lookup(session, "external." + domain)
    config.add_arg(configuration.Arg.Subnet("ExternalSubnet",
                                            internal_subnet_id,
                                            "ID of External Subnet to create resources in"))

    internal_sg_id = lib.sg_lookup(session, vpc_id, "internal." + domain)
    config.add_arg(configuration.Arg.SecurityGroup("InternalSecurityGroup",
                                                   internal_sg_id,
                                                   "ID of internal Security Group"))

    config.add_ec2_instance("Auth",
                            "auth." + domain,
                            lib.ami_lookup(session, "auth.boss"),
                            keypair,
                            subnet = "ExternalSubnet",
                            public_ip = True,
                            security_groups = ["InternalSecurityGroup", "AuthSecurityGroup"])

    config.add_security_group("AuthSecurityGroup",
                              "http",
                              [("tcp", "8080", "8080", "128.244.0.0/16"),
                               ("tcp", "22", "22", INCOMING_SUBNET)])

    listeners = [lib.create_elb_listener("8080", "8080", "HTTP"),
                 lib.create_elb_listener("9990", "9990", "HTTP")]

    config.add_loadbalancer("LoadBalancerAuth",
                            "elb-auth." + domain,
                            listeners,
                            instances=["Auth"],
                            subnets=["ExternalSubnet"], # eventually use find_all_availability_zones()
                            healthcheck_target="HTTP:8080/index.html",
                            security_groups=["InternalSecurityGroup", "AuthSecurityGroup"],
                            depends_on=["AuthSecurityGroup"])

    return config


def upload_realm_config(port, password):
    URL = "http://localhost:{}".format(port)

    kc = lib.KeyCloakClient(URL)
    kc.login("admin", password)
    if kc.token is None:
        print("Could not upload BOSS.realm configuration, exiting...")
        return

    cur_dir = os.path.dirname(os.path.realpath(__file__))
    realm_file = os.path.normpath(os.path.join(cur_dir, "..", "..", "salt_stack", "salt", "keycloak", "files", "BOSS.realm"))
    print("Opening realm file at '{}'".format(realm_file))
    with open(realm_file, "r") as fh:
        realm = json.load(fh)

    kc.create_realm(realm)
    kc.logout()

def configure_keycloak(session, domain):
    # NOTE DP: if there is an ELB in front of the auth server, this needs to be
    #          the public DNS address of the ELB.
    auth_dns = lib.elb_public_lookup(session, "elb-auth." + domain)
    auth_discovery_url = "http://{}:8080/auth/realms/BOSS".format(auth_dns)

    password = lib.generate_password()
    print("Setting Admin password to: " + password)

    call = lib.ExternalCalls(session, keypair, domain)

    call.vault_write("secret/auth", password = password, username = "admin")
    call.vault_update("secret/endpoint/auth", url = auth_discovery_url, client_id = "endpoint")

    call.set_ssh_target("auth")
    call.ssh("/srv/keycloak/bin/add-user.sh -r master -u admin -p " + password)
    call.ssh("sudo service keycloak stop")
    call.ssh("sudo killall java") # the daemon command used by the keycloak service doesn't play well with standalone.sh
                             # make sure the process is actually killed
    call.ssh("sudo service keycloak start")

    time.sleep(15) # wait for service to start
    call.ssh_tunnel(lambda p: upload_realm_config(p, password), 8080)

def generate(folder, domain):
    """Create the configuration and save it to disk"""
    name = lib.domain_to_stackname("auth." + domain)
    config = create_config(None, domain)
    config.generate(name, folder)

def create(session, domain):
    """Create the configuration, launch it, and initialize Vault"""
    name = lib.domain_to_stackname("auth." + domain)
    config = create_config(session, domain)

    success = config.create(session, name)
    if success:
        try:
            time.sleep(15)
            configure_keycloak(session, domain)
        except requests.exceptions.ConnectionError:
            print("Could not connect to Vault")

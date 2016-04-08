# Copyright 2016 The Johns Hopkins University Applied Physics Laboratory
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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

    # do a couple of verification checks
    if config.subnet_domain is not None:
        raise Exception("Invalid VPC domain name")

    if session is not None and lib.vpc_id_lookup(session, domain) is not None:
        raise Exception("VPC already exists, exiting...")

    global keypair
    keypair = lib.keypair_lookup(session)

    config.add_vpc()

    # Create the internal and external subnets
    config.subnet_domain = "internal." + domain
    config.subnet_subnet = hosts.lookup(config.subnet_domain)
    config.add_subnet("InternalSubnet")

    config.subnet_domain = "external." + domain
    config.subnet_subnet = hosts.lookup(config.subnet_domain)
    config.add_subnet("ExternalSubnet")

    subnets = []
    for az, sub in lib.azs_lookup(session):
        name = sub.capitalize() + "Subnet"
        config.subnet_domain = sub + "." + domain
        config.subnet_subnet = hosts.lookup(config.subnet_domain)
        config.add_subnet(name, az = az)
        subnets.append(name)

    # Create the user data for Vault. No data is given to Bastion
    # because it is an AWS AMI designed for NAT work and does not
    # have bossutils to use the user data config.
    user_data = configuration.UserData()
    user_data["system"]["fqdn"] = "vault." + domain
    user_data["system"]["type"] = "vault"

    config.add_ec2_instance("Vault",
                            "vault." + domain,
                            lib.ami_lookup(session, "vault.boss"),
                            keypair,
                            subnet = "InternalSubnet",
                            security_groups = ["InternalSecurityGroup"],
                            user_data = str(user_data))

    config.add_ec2_instance("Bastion",
                            "bastion." + domain,
                            lib.ami_lookup(session, "amzn-ami-vpc-nat-hvm-2015.03.0.x86_64-ebs"),
                            keypair,
                            subnet = "ExternalSubnet",
                            public_ip = True,
                            iface_check = False,
                            security_groups = ["InternalSecurityGroup", "BastionSecurityGroup"])

    config.add_ec2_instance("Auth",
                            "auth." + domain,
                            lib.ami_lookup(session, "auth.boss"),
                            keypair,
                            subnet = "InternalSubnet", # Eventually place in a autoscale group across all subnets
                            security_groups = ["InternalSecurityGroup"])

    config.add_loadbalancer("LoadBalancerAuth",
                            "elb-auth." + domain,
                            [lib.create_elb_listener("8080", "8080", "HTTP")],
                            instances = ["Auth"],
                            subnets = ["ExternalSubnet"],
                            healthcheck_target = "HTTP:8080/index.html",
                            security_groups = ["InternalSecurityGroup", "AuthSecurityGroup"],
                            depends_on = ["AuthSecurityGroup"])

    config.add_security_group("InternalSecurityGroup",
                              "internal",
                              [("-1", "-1", "-1", "10.0.0.0/8")])

    # Allow SSH access to bastion from anywhere
    config.add_security_group("BastionSecurityGroup",
                              "ssh",
                              [("tcp", "22", "22", INCOMING_SUBNET)])

    config.add_security_group("AuthSecurityGroup",
                              "auth",
                              [("tcp", "8080", "8080", "0.0.0.0/0")])

    # Create the internal route table to route traffic to the NAT Bastion
    config.add_route_table("InternalRouteTable",
                           "internal",
                           subnets = ["InternalSubnet"])

    config.add_route_table_route("InternalNatRoute",
                                 "InternalRouteTable",
                                 instance = "Bastion",
                                 depends_on = "Bastion")

    # Create the internet gateway and internet router
    config.add_route_table("InternetRouteTable",
                           "internet",
                           subnets = ["ExternalSubnet"])

    config.add_route_table_route("InternetRoute",
                                 "InternetRouteTable",
                                 gateway = "InternetGateway",
                                 depends_on = "AttachInternetGateway")

    config.add_internet_gateway("InternetGateway")

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
    name = lib.domain_to_stackname("core." + domain)
    config = create_config(None, domain)
    config.generate(name, folder)

def create(session, domain):
    """Create the configuration, launch it, and initialize Vault"""
    name = lib.domain_to_stackname("core." + domain)
    config = create_config(session, domain)

    success = config.create(session, name)
    if success:
        vpc_id = lib.vpc_id_lookup(session, domain)
        lib.rt_name_default(session, vpc_id, "internal." + domain)

        try:
            print("Waiting 1 minute for VMs to start...")
            time.sleep(60)

            print("Initializing Vault...")
            initialized = False
            for i in range(6):
                try:
                    call = lib.ExternalCalls(session, keypair, domain)
                    call.vault("vault-init")
                    initialized = True
                    break
                except requests.exceptions.ConnectionError:
                    time.sleep(30)
            if not initialized:
                raise Exception("Could not initialize Vault")

            print("Configuring KeyCloak...")
            configure_keycloak(session, domain)

            # Tell Scalyr to get CloudWatch metrics for these instances.
            instances = [ "vault." + domain ]
            scalyr.add_instances_to_scalyr(session, CORE_REGION, instances)
        except:
            print("Could not connect to Vault, manually initialize it before launching other machines")
            # If Vault fails to initialize then KeyCloak also needs to be configured...

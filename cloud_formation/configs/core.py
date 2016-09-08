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

AUTH_CLUSTER_SIZE = { # Auth Server Cluster is a fixed size
    "development" : 1,
    "production": 3 # should be an odd number
}

CONSUL_CLUSTER_SIZE = { # Consul Cluster is a fixed size
    "development" : 1,
    "production": 5 # can tolerate 2 failures
}

VAULT_CLUSTER_SIZE = { # Vault Cluster is a fixed size
    "development" : 1,
    "production": 3 # should be an odd number
}

def create_asg_elb(config, key, hostname, ami, keypair, user_data, size, isubnets, esubnets, listeners, check, sgs=[], role = None, public=True, depends_on=None):
    security_groups = ["InternalSecurityGroup"]
    config.add_autoscale_group(key,
                               hostname,
                               ami,
                               keypair,
                               subnets = isubnets,
                               security_groups = security_groups,
                               user_data = user_data,
                               min = size,
                               max = size,
                               elb = key + "LoadBalancer",
                               notifications = "DNSSNS",
                               role = role,
                               depends_on = key + "LoadBalancer")

    security_groups.extend(sgs)
    config.add_loadbalancer(key + "LoadBalancer",
                            hostname,
                            listeners,
                            subnets = esubnets if public else isubnets,
                            healthcheck_target = check,
                            security_groups = security_groups,
                            public = public,
                            depends_on = depends_on)

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

    internal_subnets, external_subnets = config.add_all_azs(session)

    # Configure Squid to allow clustered Vault access, restricted to connections from the Bastion
    user_data = """#cloud-config
packages:
    - squid

write_files:
    - content: |
            acl localhost src 127.0.0.1/32 ::1
            acl to_localhost dst 127.0.0.0/8 0.0.0.0/32 ::1
            acl localnet dst 10.0.0.0/8
            acl Safe_ports port 8200

            http_access deny !Safe_ports
            http_access deny !localnet
            http_access deny to_localhost
            http_access allow localhost
            http_access deny all

            http_port 3128
      path: /etc/squid/squid.conf
      owner: root squid
      permissions: '0644'

runcmd:
    - chkconfig squid on
    - service squid start
    """
    config.add_ec2_instance("Bastion",
                            "bastion." + domain,
                            lib.ami_lookup(session, "amzn-ami-vpc-nat-hvm-2015.03.0.x86_64-ebs"),
                            keypair,
                            subnet = "ExternalSubnet",
                            public_ip = True,
                            iface_check = False,
                            user_data = user_data,
                            security_groups = ["InternalSecurityGroup", "BastionSecurityGroup"],
                            depends_on = "AttachInternetGateway")

    user_data = configuration.UserData()
    user_data["system"]["fqdn"] = "consul." + domain
    user_data["system"]["type"] = "consul"
    user_data["consul"]["cluster"] = str(configuration.get_scenario(CONSUL_CLUSTER_SIZE))
    #consul_role = lib.role_arn_lookup(session, 'consul')
    consul_role = lib.instance_profile_arn_lookup(session, 'consul')
    print(consul_role)
    config.add_autoscale_group("Consul",
                               "consul." + domain,
                               lib.ami_lookup(session, "consul.boss"),
                               keypair,
                               subnets = internal_subnets,
                               security_groups = ["InternalSecurityGroup"],
                               user_data = str(user_data),
                               min = CONSUL_CLUSTER_SIZE,
                               max = CONSUL_CLUSTER_SIZE,
                               notifications = "DNSSNS",
                               role = consul_role,
                               depends_on = ["DNSLambda", "DNSSNS", "DNSLambdaExecute"])

    user_data = configuration.UserData()
    user_data["system"]["fqdn"] = "vault." + domain
    user_data["system"]["type"] = "vault"
    config.add_autoscale_group("Vault",
                               "vault." + domain,
                               lib.ami_lookup(session, "vault.boss"),
                               keypair,
                               subnets = internal_subnets,
                               security_groups = ["InternalSecurityGroup"],
                               user_data = str(user_data),
                               min = VAULT_CLUSTER_SIZE,
                               max = VAULT_CLUSTER_SIZE,
                               notifications = "DNSSNS",
                               depends_on = ["Consul", "DNSLambda", "DNSSNS", "DNSLambdaExecute"])


    user_data = configuration.UserData()
    user_data["system"]["fqdn"] = "auth." + domain
    user_data["system"]["type"] = "auth"
    deps = ["AuthSecurityGroup", "AttachInternetGateway", "DNSLambda", "DNSSNS", "DNSLambdaExecute"]

    SCENARIO = os.environ["SCENARIO"]
    USE_DB = SCENARIO in ("production",)
    # Problem: If development scenario uses a local DB. If the auth server crashes
    #          and is auto restarted by the autoscale group then the new auth server
    #          will not have any of the previous configuration, because the old DB
    #          was lost. Using an RDS for development fixes this at the cost of having
    #          the core config taking longer to launch.
    if USE_DB:
        deps.append("AuthDB")
        user_data["aws"]["db"] = "keycloak" # flag for init script for which config to use

    if domain in hosts.BASE_DOMAIN_CERTS.keys():
        cert = lib.cert_arn_lookup(session, "auth." + hosts.BASE_DOMAIN_CERTS[domain])
    else:
        cert = lib.cert_arn_lookup(session, "auth.integration.theboss.io")

    create_asg_elb(config,
                   "Auth",
                   "auth." + domain,
                   lib.ami_lookup(session, "auth.boss"),
                   keypair,
                   str(user_data),
                   AUTH_CLUSTER_SIZE,
                   internal_subnets,
                   external_subnets,
                   [("443", "8080", "HTTPS", cert)],
                   "HTTP:8080/index.html",
                   sgs = ["AuthSecurityGroup"],
                   depends_on=deps)

    if USE_DB:
        config.add_rds_db("AuthDB",
                          "auth-db." + domain,
                          "3306",
                          "keycloak",
                          "keycloak",
                          "keycloak",
                          internal_subnets,
                          type_ = "db.t2.micro",
                          security_groups = ["InternalSecurityGroup"])


    config.add_lambda("DNSLambda",
                      "dns." + domain,
                      "DNSLambdaRole",
                      "lambda/updateRoute53/index.py",
                      handler="index.handler",
                      timeout=10,
                      depends_on="DNSZone")
    role = lib.role_arn_lookup(session, 'UpdateRoute53')

    config.add_arg(configuration.Arg.String("DNSLambdaRole", role,
                                            "IAM role for Lambda dns." + domain))

    config.add_lambda_permission("DNSLambdaExecute", "DNSLambda")

    config.add_sns_topic("DNSSNS",
                         "dns." + domain,
                         "dns." + domain,
                         [("lambda", {"Fn::GetAtt": ["DNSLambda", "Arn"]})])


    config.add_security_group("InternalSecurityGroup",
                              "internal",
                              [("-1", "-1", "-1", "10.0.0.0/8")])

    # Allow SSH access to bastion from anywhere
    config.add_security_group("BastionSecurityGroup",
                              "ssh",
                              [("tcp", "22", "22", INCOMING_SUBNET)])

    config.add_security_group("AuthSecurityGroup",
                              "auth",
                              [("tcp", "443", "443", "0.0.0.0/0")])

    # Create the internal route table to route traffic to the NAT Bastion
    internal_subnets.append("InternalSubnet")
    config.add_route_table("InternalRouteTable",
                           "internal",
                           subnets = internal_subnets)

    config.add_route_table_route("InternalNatRoute",
                                 "InternalRouteTable",
                                 instance = "Bastion",
                                 depends_on = "Bastion")

    # Create the internet gateway and internet router
    external_subnets.append("ExternalSubnet")
    config.add_route_table("InternetRouteTable",
                           "internet",
                           subnets = external_subnets)

    config.add_route_table_route("InternetRoute",
                                 "InternetRouteTable",
                                 gateway = "InternetGateway",
                                 depends_on = "AttachInternetGateway")

    config.add_internet_gateway("InternetGateway")

    return config

def upload_realm_config(port, username, password, realm_username, realm_password):
    URL = "http://localhost:{}".format(port) # TODO move out of tunnel and use public address

    kc = lib.KeyCloakClient(URL)
    kc.login(username, password)
    if kc.token is None:
        print("Could not upload BOSS.realm configuration, exiting...")
        return

    cur_dir = os.path.dirname(os.path.realpath(__file__))
    realm_file = os.path.normpath(os.path.join(cur_dir, "..", "..", "salt_stack", "salt", "keycloak", "files", "BOSS.realm"))
    print("Opening realm file at '{}'".format(realm_file))
    with open(realm_file, "r") as fh:
        realm = json.load(fh)

    try:
        realm["users"][0]["username"] = realm_username
        realm["users"][0]["credentials"][0]["value"] = realm_password
    except:
        print("Could not set realm admin's username or password, not creating user")
        if "users" in realm:
            del realm["users"]

    kc.create_realm(realm)
    kc.logout()

def configure_keycloak(session, domain):
    # NOTE DP: if there is an ELB in front of the auth server, this needs to be
    #          the public DNS address of the ELB.
    auth_elb = lib.elb_public_lookup(session, "auth." + domain)

    if domain in hosts.BASE_DOMAIN_CERTS.keys():
        auth_domain = 'auth.' + hosts.BASE_DOMAIN_CERTS[domain]
        auth_discovery_url = "https://{}/auth/realms/BOSS".format(auth_domain)
        lib.set_domain_to_dns_name(session, auth_domain, auth_elb)
    else:
        auth_discovery_url = "https://{}/auth/realms/BOSS".format(auth_elb)

    username = "admin"
    password = lib.generate_password()
    realm_username = "bossadmin"
    realm_password = lib.generate_password()

    call = lib.ExternalCalls(session, keypair, domain)

    call.vault_write("secret/auth", password = password, username = username, client_id = "admin-cli")
    call.vault_write("secret/auth/realm", username = realm_username, password = realm_password, client_id = "endpoint")
    call.vault_update("secret/keycloak", password = password, username = username, client_id = "admin-cli")
    call.vault_update("secret/endpoint/auth", url = auth_discovery_url, client_id = "endpoint")
    call.vault_update("secret/proofreader/auth", url = auth_discovery_url, client_id = "endpoint")

    call.set_ssh_target("auth")
    call.ssh("/srv/keycloak/bin/add-user.sh -r master -u {} -p {}".format(username, password))
    call.ssh("sudo service keycloak stop")
    time.sleep(2)
    call.ssh("sudo killall java") # the daemon command used by the keycloak service doesn't play well with standalone.sh
                                  # make sure the process is actually killed
    time.sleep(3)
    call.ssh("sudo service keycloak start")
    print("Waiting for Keycloak to restart")
    time.sleep(75)

    upload = lambda p: upload_realm_config(p, username, password, realm_username, realm_password)
    call.ssh_tunnel(upload, 8080)

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

        print("Waiting 1 minute for VMs to start...")
        time.sleep(60)
        post_init(session, domain)

def post_init(session, domain):
    global keypair
    if keypair is None:
        keypair = lib.keypair_lookup(session)

    print("Initializing Vault...")
    initialized = False
    for i in range(6):
        try:
            call = lib.ExternalCalls(session, keypair, domain)
            call.vault_init()
            initialized = True
            break
        except requests.exceptions.ConnectionError:
            time.sleep(30)
    if not initialized:
        print("Could not initialize Vault, manually call post-init before launching other machines")
        return

    print("Waiting for Keycloak to bootstrap")
    time.sleep(75)

    print("Configuring Keycloak...")
    configure_keycloak(session, domain)

    # Tell Scalyr to get CloudWatch metrics for these instances.
    instances = [ "vault." + domain ]
    scalyr.add_instances_to_scalyr(session, CORE_REGION, instances)

def delete(session, domain):
    # NOTE: CloudWatch logs for the DNS Lambda are not deleted
    lib.route53_delete_records(session, domain, "auth." + domain)
    lib.route53_delete_records(session, domain, "consul." + domain)
    lib.route53_delete_records(session, domain, "vault." + domain)
    lib.sns_unsubscribe_all(session, "dns." + domain, )
    lib.delete_stack(session, domain, "core")

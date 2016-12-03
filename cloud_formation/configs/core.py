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
import hvac
from concurrent.futures import ThreadPoolExecutor

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

TIMEOUT_VAULT = 120
TIMEOUT_KEYCLOAK = 120


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
                               support_update = False, # Update will restart the instances manually
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
        cert = lib.cert_arn_lookup(session, "auth-{}.{}".format(domain.split(".")[0],
                                                                hosts.DEV_DOMAIN))
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

        post_init(session, domain)

def post_init(session, domain, startup_wait=False):
    # Keypair is needed by ExternalCalls
    global keypair
    if keypair is None:
        keypair = lib.keypair_lookup(session)
    call = lib.ExternalCalls(session, keypair, domain)

    # Figure out the external domain name of the auth server(s), matching the SSL cert
    if domain in hosts.BASE_DOMAIN_CERTS.keys():
        auth_domain = 'auth.' + hosts.BASE_DOMAIN_CERTS[domain]
    else:
        auth_domain = 'auth-{}.{}'.format(domain.split(".")[0], hosts.DEV_DOMAIN)

    # OIDC Discovery URL
    auth_discovery_url = "https://{}/auth/realms/BOSS".format(auth_domain)

    # Configure external DNS
    auth_elb = lib.elb_public_lookup(session, "auth." + domain)
    lib.set_domain_to_dns_name(session, auth_domain, auth_elb, lib.get_hosted_zone(session))

    # Generate initial user accounts
    username = "admin"
    password = lib.generate_password()
    realm_username = "bossadmin"
    realm_password = lib.generate_password()

    # Initialize Vault
    print("Waiting for Vault...")
    call.vault_check(TIMEOUT_VAULT) # Expecting this to also check Consul

    print("Initializing Vault...")
    try:
        call.vault_init()
    except Exception as ex:
        print(ex)
        print("Could not initialize Vault")
        print("Call: {}".format(lib.get_command("post-init")))
        print("Before launching other stacks")
        return

    # Write data into Vault
    print("Writing secret/auth")
    call.vault_write("secret/auth", password = password, username = username, client_id = "admin-cli")
    print("Writing secret/auth/realm")
    call.vault_write("secret/auth/realm", username = realm_username, password = realm_password, client_id = "endpoint")
    print("Updating secret/keycloak")
    call.vault_update("secret/keycloak", password = password, username = username, client_id = "admin-cli", realm = "master")
    # DP TODO: Move this update call into the api config
    print("Updating secret/endpoint/auth")
    call.vault_update("secret/endpoint/auth", url = auth_discovery_url, client_id = "endpoint")
    # DP TODO: Move this update call into the proofreader config
    print("Updating secret/proofreader/auth")
    call.vault_update("secret/proofreader/auth", url = auth_discovery_url, client_id = "endpoint")

    # Configure Keycloak
    print("Waiting for Keycloak to bootstrap")
    call.keycloak_check(TIMEOUT_KEYCLOAK)

    #######
    ## DP TODO: Need to find a check so that the master user is only added once to keycloak
    ##          Also need to guard the writes to vault with the admin password
    #######

    print("Creating initial Keycloak admin user")
    call.set_ssh_target("auth")
    call.ssh("/srv/keycloak/bin/add-user.sh -r master -u {} -p {}".format(username, password))

    print("Restarting Keycloak")
    call.ssh("sudo service keycloak stop")
    time.sleep(2)
    call.ssh("sudo killall java") # the daemon command used by the keycloak service doesn't play well with standalone.sh
                                  # make sure the process is actually killed
    time.sleep(3)
    call.ssh("sudo service keycloak start")

    print("Waiting for Keycloak to restart")
    call.keycloak_check(TIMEOUT_KEYCLOAK)

    def upload_realm_config(port):
        URL = "http://localhost:{}".format(port) # TODO move out of tunnel and use public address

        kc = lib.KeyCloakClient(URL)
        kc.login(username, password)

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

        print("Uploading BOSS.realm configuration")
        kc.create_realm(realm)
        kc.logout()
    call.ssh_tunnel(upload_realm_config, 8080)


    # Tell Scalyr to get CloudWatch metrics for these instances.
    instances = [ "vault." + domain ]
    scalyr.add_instances_to_scalyr(session, CORE_REGION, instances)

def update(session, domain):
    # Only in the production scenario will data be preserved over the update
    if os.environ["SCENARIO"] not in ("production",):
        print("Can only update the production scenario")
        return None

    consul_update_timeout = 5 # minutes
    consul_size = int(configuration.get_scenario(CONSUL_CLUSTER_SIZE))
    min_time = consul_update_timeout * consul_size
    max_time = min_time + 5 # add some time to allow the CF update to happen

    print("Update command will take {} - {} minutes to finish".format(min_time, max_time))
    print("Stack will be available during that time")
    resp = input("Update? [N/y] ")
    if len(resp) == 0 or resp[0] not in ('y', 'Y'):
        print("Canceled")
        return

    name = lib.domain_to_stackname("core." + domain)
    config = create_config(session, domain)

    success = config.update(session, name)

    if success:
        keypair = lib.keypair_lookup(session)
        call = lib.ExternalCalls(session, keypair, domain)

        # Unseal Vault first, so the rest of the system can continue working
        print("Waiting for Vault...")
        if not call.vault_check(90, exception=False):
            print("Could not contact Vault, check networking and run the following command")
            print("python3 bastion.py bastion.521.boss vault.521.boss vault-unseal")
            return

        call.vault_unseal()

        print("Stack should be ready for use")
        print("Starting to cycle consul cluster instances")

        # DP NOTE: Cycling the instances is done manually (outside of CF)
        #          so that Vault can be unsealed first, else the whole stacks
        #          would not be usable until all consul instance were restarted
        with ThreadPoolExecutor(max_workers=3) as tpe:
            # Need time for the ASG to detect the terminated instance,
            # launch the new instance, and have the instance cluster
            tpe.submit(lib.asg_restart,
                            session,
                            "consul." + domain,
                            consul_update_timeout * 60)

    return success

def delete(session, domain):
    # NOTE: CloudWatch logs for the DNS Lambda are not deleted
    lib.route53_delete_records(session, domain, "auth." + domain)
    lib.route53_delete_records(session, domain, "consul." + domain)
    lib.route53_delete_records(session, domain, "vault." + domain)
    lib.sns_unsubscribe_all(session, "dns." + domain, )
    lib.delete_stack(session, domain, "core")

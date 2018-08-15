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

from lib.cloudformation import CloudFormationConfiguration, Ref, Arn, get_scenario
from lib.userdata import UserData
from lib.names import AWSNames
from lib.keycloak import KeyCloakClient
from lib.external import ExternalCalls
from lib import aws
from lib import utils
from lib import scalyr
from lib import constants as const

import os
import sys
import json
import time
from concurrent.futures import ThreadPoolExecutor

keypair = None

def create_asg_elb(config, key, hostname, ami, keypair, user_data, size, isubnets, esubnets, listeners, check, sgs=[], role = None, public=True, depends_on=None):
    security_groups = [Ref("InternalSecurityGroup")]
    config.add_autoscale_group(key,
                               hostname,
                               ami,
                               keypair,
                               subnets = isubnets,
                               security_groups = security_groups,
                               user_data = user_data,
                               min = size,
                               max = size,
                               elb = Ref(key + "LoadBalancer"),
                               notifications = Ref("DNSSNS"),
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
    config = CloudFormationConfiguration('core', domain, const.REGION)
    names = AWSNames(domain)

    global keypair
    # keypair = aws.keypair_lookup(session)
    keypair = None
    config.add_vpc()

    # Create the internal and external subnets
    config.add_subnet('InternalSubnet', names.subnet('internal'))
    config.add_subnet('ExternalSubnet', names.subnet('external'))
    internal_subnets, external_subnets = config.add_all_azs(session)
    # it seems that both Lambdas and ASGs needs lambda_compatible_only subnets.
    internal_subnets_lambda, external_subnets_lambda = config.add_all_azs(session, lambda_compatible_only=True)

    config.add_ec2_instance("Bastion",
                            names.bastion,
                            aws.ami_lookup(session, const.BASTION_AMI),
                            keypair,
                            subnet = Ref("ExternalSubnet"),
                            public_ip = True,
                            user_data = const.BASTION_USER_DATA,
                            security_groups = [Ref("InternalSecurityGroup"), Ref("BastionSecurityGroup")],
                            depends_on = "AttachInternetGateway")

    user_data = UserData()
    user_data["system"]["fqdn"] = names.consul
    user_data["system"]["type"] = "consul"
    user_data["consul"]["cluster"] = str(get_scenario(const.CONSUL_CLUSTER_SIZE))
    config.add_autoscale_group("Consul",
                               names.consul,
                               aws.ami_lookup(session, "consul.boss"),
                               keypair,
                               subnets = internal_subnets_lambda,
                               security_groups = [Ref("InternalSecurityGroup")],
                               user_data = str(user_data),
                               min = const.CONSUL_CLUSTER_SIZE,
                               max = const.CONSUL_CLUSTER_SIZE,
                               notifications = Ref("DNSSNS"),
                               role = aws.instance_profile_arn_lookup(session, 'consul'),
                               support_update = False, # Update will restart the instances manually
                               depends_on = ["DNSLambda", "DNSSNS", "DNSLambdaExecute"])

    user_data = UserData()
    user_data["system"]["fqdn"] = names.vault
    user_data["system"]["type"] = "vault"
    config.add_autoscale_group("Vault",
                               names.vault,
                               aws.ami_lookup(session, "vault.boss"),
                               keypair,
                               subnets = internal_subnets_lambda,
                               security_groups = [Ref("InternalSecurityGroup")],
                               user_data = str(user_data),
                               min = const.VAULT_CLUSTER_SIZE,
                               max = const.VAULT_CLUSTER_SIZE,
                               notifications = Ref("DNSSNS"),
                               depends_on = ["Consul", "DNSLambda", "DNSSNS", "DNSLambdaExecute"])


    user_data = UserData()
    user_data["system"]["fqdn"] = names.auth
    user_data["system"]["type"] = "auth"
    deps = ["AuthSecurityGroup",
            "AttachInternetGateway",
            "DNSLambda",
            "DNSSNS",
            "DNSLambdaExecute"]

    SCENARIO = os.environ["SCENARIO"]
    USE_DB = SCENARIO in ("production", "ha-development",)
    # Problem: If development scenario uses a local DB. If the auth server crashes
    #          and is auto restarted by the autoscale group then the new auth server
    #          will not have any of the previous configuration, because the old DB
    #          was lost. Using an RDS for development fixes this at the cost of having
    #          the core config taking longer to launch.
    if USE_DB:
        deps.append("AuthDB")
        user_data["aws"]["db"] = "keycloak" # flag for init script for which config to use

    cert = aws.cert_arn_lookup(session, names.public_dns('auth'))
    create_asg_elb(config,
                   "Auth",
                   names.auth,
                   aws.ami_lookup(session, "auth.boss"),
                   keypair,
                   str(user_data),
                   const.AUTH_CLUSTER_SIZE,
                   internal_subnets_lambda,
                   external_subnets_lambda,
                   [("443", "8080", "HTTPS", cert)],
                   "HTTP:8080/index.html",
                   sgs = [Ref("AuthSecurityGroup")],
                   depends_on=deps)

    if USE_DB:
        config.add_rds_db("AuthDB",
                          names.auth_db,
                          "3306",
                          "keycloak",
                          "keycloak",
                          "keycloak",
                          internal_subnets,
                          type_ = "db.t2.micro",
                          security_groups = [Ref("InternalSecurityGroup")])


    config.add_lambda("DNSLambda",
                      names.dns,
                      aws.role_arn_lookup(session, 'UpdateRoute53'),
                      const.DNS_LAMBDA,
                      handler="index.handler",
                      timeout=10,
                      depends_on="DNSZone")

    config.add_lambda_permission("DNSLambdaExecute", Ref("DNSLambda"))

    config.add_sns_topic("DNSSNS",
                         names.dns,
                         names.dns,
                         [("lambda", Arn("DNSLambda"))])


    config.add_security_group("InternalSecurityGroup",
                              names.internal,
                              [("-1", "-1", "-1", "10.0.0.0/8")])

    # Allow SSH access to bastion from anywhere
    config.add_security_group("BastionSecurityGroup",
                              names.ssh,
                              [("tcp", "22", "22", const.INCOMING_SUBNET)])

    config.add_security_group("AuthSecurityGroup",
                              #names.https, DP XXX: hack until we can get production updated correctly
                              names.auth,
                              [("tcp", "443", "443", "0.0.0.0/0")])

    # Create the internal route table to route traffic to the NAT Bastion
    all_internal_subnets = internal_subnets.copy()
    all_internal_subnets.append(Ref("InternalSubnet"))
    config.add_route_table("InternalRouteTable",
                           names.internal,
                           subnets = all_internal_subnets)

    config.add_route_table_route("InternalNatRoute",
                                 Ref("InternalRouteTable"),
                                 nat = Ref("NAT"),
                                 depends_on = "NAT")

    # Create the internet gateway and internet router
    all_external_subnets = external_subnets.copy()
    all_external_subnets.append(Ref("ExternalSubnet"))
    config.add_route_table("InternetRouteTable",
                           names.internet,
                           subnets = all_external_subnets)

    config.add_route_table_route("InternetRoute",
                                 Ref("InternetRouteTable"),
                                 gateway = Ref("InternetGateway"),
                                 depends_on = "AttachInternetGateway")

    config.add_internet_gateway("InternetGateway", names.internet)
    config.add_endpoint("S3Endpoint", "s3", [Ref("InternalRouteTable")])
    config.add_nat("NAT", Ref("ExternalSubnet"), depends_on="AttachInternetGateway")

    return config

def generate(session, domain):
    """Create the configuration and save it to disk"""
    config = create_config(session, domain)
    config.generate()

def create(session, domain):
    """Create the configuration, launch it, and initialize Vault"""
    config = create_config(session, domain)

    success = config.create(session)
    if success:
        vpc_id = aws.vpc_id_lookup(session, domain)
        aws.rt_name_default(session, vpc_id, "default." + domain)

        post_init(session, domain)

def post_init(session, domain, startup_wait=False):
    # Keypair is needed by ExternalCalls
    global keypair
    if keypair is None:
        keypair = aws.keypair_lookup(session)
    call = ExternalCalls(session, keypair, domain)
    names = AWSNames(domain)

    # Figure out the external domain name of the auth server(s), matching the SSL cert
    auth_domain = names.public_dns("auth")

    # OIDC Discovery URL
    auth_discovery_url = "https://{}/auth/realms/BOSS".format(auth_domain)

    # Configure external DNS
    auth_elb = aws.elb_public_lookup(session, names.auth)
    aws.set_domain_to_dns_name(session, auth_domain, auth_elb, aws.get_hosted_zone(session))

    # Generate initial user accounts
    username = "admin"
    password = utils.generate_password()
    realm_username = "bossadmin"
    realm_password = utils.generate_password()

    # Initialize Vault
    print("Waiting for Vault...")
    call.check_vault(const.TIMEOUT_VAULT)  # Expecting this to also check Consul

    with call.vault() as vault:
        print("Initializing Vault...")
        try:
            vault.initialize()
        except Exception as ex:
            print(ex)
            print("Could not initialize Vault")
            print("Call: {}".format(utils.get_command("post-init")))
            print("Before launching other stacks")
            return

        #Check and see if these secrets already exist before we overwrite them with new ones.
        # Write data into Vault
        if not vault.read(const.VAULT_AUTH):
            print("Writing {}".format(const.VAULT_AUTH))
            vault.write(const.VAULT_AUTH, password = password, username = username, client_id = "admin-cli")

        if not vault.read(const.VAULT_REALM):
            print("Writing {}".format(const.VAULT_REALM))
            vault.write(const.VAULT_REALM, username = realm_username, password = realm_password, client_id = "endpoint")

        if not vault.read(const.VAULT_KEYCLOAK):
            print("Updating {}".format(const.VAULT_KEYCLOAK))
            vault.update(const.VAULT_KEYCLOAK, password = password, username = username, client_id = "admin-cli", realm = "master")

        if not vault.read(const.VAULT_ENDPOINT_AUTH):
            # DP TODO: Move this update call into the api config
            print("Updating {}".format(const.VAULT_ENDPOINT_AUTH))
            vault.update(const.VAULT_ENDPOINT_AUTH, url = auth_discovery_url, client_id = "endpoint")

        if not vault.read(const.VAULT_PROOFREAD_AUTH):
            # DP TODO: Move this update call into the proofreader config
            print("Updating {}".format(const.VAULT_PROOFREAD_AUTH))
            vault.update(const.VAULT_PROOFREAD_AUTH, url = auth_discovery_url, client_id = "endpoint")

    # Configure Keycloak
    print("Waiting for Keycloak to bootstrap")
    call.check_keycloak(const.TIMEOUT_KEYCLOAK)

    #######
    ## DP TODO: Need to find a check so that the master user is only added once to keycloak
    ##          Also need to guard the writes to vault with the admin password
    #######

    with call.ssh(names.auth) as ssh:
        print("Creating initial Keycloak admin user")
        ssh("/srv/keycloak/bin/add-user.sh -r master -u {} -p {}".format(username, password))

        print("Restarting Keycloak")
        ssh("sudo service keycloak stop")
        time.sleep(2)
        ssh("sudo killall java") # the daemon command used by the keycloak service doesn't play well with standalone.sh
                                      # make sure the process is actually killed
        time.sleep(3)
        ssh("sudo service keycloak start")

    print("Waiting for Keycloak to restart")
    call.check_keycloak(const.TIMEOUT_KEYCLOAK)

    with call.tunnel(names.auth, 8080) as port:
        URL = "http://localhost:{}".format(port) # TODO move out of tunnel and use public address

        with KeyCloakClient(URL, username, password) as kc:
            print("Opening realm file at '{}'".format(const.KEYCLOAK_REALM))
            with open(const.KEYCLOAK_REALM, "r") as fh:
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

    # Tell Scalyr to get CloudWatch metrics for these instances.
    instances = [ names.vault ]
    scalyr.add_instances_to_scalyr(session, const.REGION, instances)

def update(session, domain):
    # Only in the production scenario will data be preserved over the update
    if os.environ["SCENARIO"] not in ("production", "ha-development",):
        print("Can only update the production and ha-development scenario")
        return None

    consul_update_timeout = 5 # minutes
    consul_size = int(get_scenario(const.CONSUL_CLUSTER_SIZE))
    min_time = consul_update_timeout * consul_size
    max_time = min_time + 5 # add some time to allow the CF update to happen

    print("Update command will take {} - {} minutes to finish".format(min_time, max_time))
    print("Stack will be available during that time")
    resp = input("Update? [N/y] ")
    if len(resp) == 0 or resp[0] not in ('y', 'Y'):
        print("Canceled")
        return

    config = create_config(session, domain)
    success = config.update(session)

    if success:
        keypair = aws.keypair_lookup(session)
        call = ExternalCalls(session, keypair, domain)
        names = AWSNames(domain)

        # Unseal Vault first, so the rest of the system can continue working
        print("Waiting for Vault...")
        if not call.check_vault(90, exception=False):
            print("Could not contact Vault, check networking and run the following command")
            print("python3 bastion.py bastion.521.boss vault.521.boss vault-unseal")
            return

        with call.vault() as vault:
            vault.unseal()

        print("Stack should be ready for use")
        print("Starting to cycle consul cluster instances")

        # DP NOTE: Cycling the instances is done manually (outside of CF)
        #          so that Vault can be unsealed first, else the whole stacks
        #          would not be usable until all consul instance were restarted
        with ThreadPoolExecutor(max_workers=3) as tpe:
            # Need time for the ASG to detect the terminated instance,
            # launch the new instance, and have the instance cluster
            tpe.submit(aws.asg_restart,
                            session,
                            names.consul,
                            consul_update_timeout * 60)

    return success

def delete(session, domain):
    # NOTE: CloudWatch logs for the DNS Lambda are not deleted
    if utils.get_user_confirm("All data will be lost. Are you sure you want to proceed?"):
        names = AWSNames(domain)
        aws.route53_delete_records(session, domain, names.auth)
        aws.route53_delete_records(session, domain, names.consul)
        aws.route53_delete_records(session, domain, names.vault)
        aws.sns_unsubscribe_all(session, names.dns)
        CloudFormationConfiguration('core', domain).delete(session)

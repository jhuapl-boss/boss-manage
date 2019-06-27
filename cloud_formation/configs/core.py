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
  * A new VPC with an internal DNS Hosted Zone
  * Internal and External subnets for every availability zone
  * A Bastion server that allows SSH access to internal machines
  * A Vault ASG clusters for secret storage
  * A Vault DynamoDB table for Vault storage of data
  * A Keycloak Authentication server ASG, ELB,  and (optional) RDS instance
  * A lambda to handle DNS updates for ASG instance changes
  * An Internet Gateway allowing network connections to the internet
  * A S3 endpoint for internal access to S3
  * A NAT instance allowing protected internet access from internal resources
    - A NAT instance is used instead of the bastion machine as it provides
      higher throughput

The core configuration create all of the infrastructure that is required for
the other production resources to function.

CHANGELOG:
    Version 1: Initial version of core config
    Version 2: Vault updates
               * Replaced Consul storage backend with DynamoDB storage backend
               * Updated Vault configuration to use AWS KMS for key storage
               * Code for migrating Vault data from Consul to DynamoDB
"""

DEPENDENCIES = None

from lib.cloudformation import CloudFormationConfiguration, Ref, Arn
from lib.userdata import UserData
from lib.keycloak import KeyCloakClient
from lib.exceptions import BossManageError, BossManageCanceled
from lib import aws
from lib import utils
from lib import console
from lib import scalyr
from lib import constants as const
from lib import console

import os
import sys
import json
import time

def create_asg_elb(config, key, hostname, ami, keypair, user_data, size, isubnets, esubnets, listeners, check, sgs=[], role = None, type_="t2.micro", public=True, depends_on=None):
    security_groups = [Ref("InternalSecurityGroup")]
    config.add_autoscale_group(key,
                               hostname,
                               ami,
                               keypair,
                               subnets = isubnets,
                               type_= type_,
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

def create_config(bosslet_config):
    """Create the CloudFormationConfiguration object."""
    config = CloudFormationConfiguration('core', bosslet_config, version="2")
    session = bosslet_config.session
    keypair = bosslet_config.SSH_KEY
    names = bosslet_config.names

    config.add_vpc()

    # Create the internal and external subnets
    config.add_subnet('InternalSubnet', names.internal.subnet)
    config.add_subnet('ExternalSubnet', names.external.subnet)
    internal_subnets, external_subnets = config.add_all_subnets()
    internal_subnets_asg, external_subnets_asg = config.find_all_subnets('asg')

    user_data = const.BASTION_USER_DATA.format(bosslet_config.NETWORK)
    config.add_ec2_instance("Bastion",
                            names.bastion.dns,
                            aws.ami_lookup(bosslet_config, const.BASTION_AMI),
                            keypair,
                            subnet = Ref("ExternalSubnet"),
                            public_ip = True,
                            user_data = user_data,
                            security_groups = [Ref("InternalSecurityGroup"), Ref("BastionSecurityGroup")],
                            depends_on = "AttachInternetGateway")

    vault_role = aws.role_arn_lookup(session, 'apl-vault')
    vault_actions = ['kms:Encrypt', 'kms:Decrypt', 'kms:DescribeKey']
    config.add_kms_key("VaultKey", names.vault.key, vault_role, vault_actions)

    config.add_dynamo_table("VaultTable", names.vault.ddb,
                            attributes = [('Path', 'S'),
                                          ('Key', 'S')],
                            key_schema = [('Path', 'HASH'),
                                          ('Key', 'RANGE')],
                            throughput = (5, 5))

    user_data = UserData()
    user_data["system"]["fqdn"] = names.vault.dns
    user_data["system"]["type"] = "vault"
    user_data["vault"]["kms_key"] = str(Ref("VaultKey"))
    user_data["vault"]["ddb_table"] = names.vault
    parsed_user_data = { "Fn::Join" : ["", user_data.format_for_cloudformation()]}
    config.add_autoscale_group("Vault",
                               names.vault.dns,
                               aws.ami_lookup(bosslet_config, names.vault.ami),
                               keypair,
                               subnets = internal_subnets_asg,
                               type_ = const.VAULT_TYPE,
                               security_groups = [Ref("InternalSecurityGroup")],
                               user_data = parsed_user_data,
                               min = const.VAULT_CLUSTER_SIZE,
                               max = const.VAULT_CLUSTER_SIZE,
                               notifications = Ref("DNSSNS"),
                               role = aws.instance_profile_arn_lookup(session, 'apl-vault'),
                               depends_on = ["VaultKey", "VaultTable", "DNSLambda", "DNSSNS", "DNSLambdaExecute"])


    user_data = UserData()
    user_data["system"]["fqdn"] = names.auth.dns
    user_data["system"]["type"] = "auth"
    deps = ["AuthSecurityGroup",
            "AttachInternetGateway",
            "DNSLambda",
            "DNSSNS",
            "DNSLambdaExecute"]

    # Problem: If development scenario uses a local DB. If the auth server crashes
    #          and is auto restarted by the autoscale group then the new auth server
    #          will not have any of the previous configuration, because the old DB
    #          was lost. Using an RDS for development fixes this at the cost of having
    #          the core config taking longer to launch.
    USE_DB = bosslet_config.AUTH_RDS
    if USE_DB:
        deps.append("AuthDB")
        user_data["aws"]["db"] = "keycloak" # flag for init script for which config to use

    cert = aws.cert_arn_lookup(session, names.public_dns('auth'))
    create_asg_elb(config,
                   "Auth",
                   names.auth.dns,
                   aws.ami_lookup(bosslet_config, names.auth.ami),
                   keypair,
                   str(user_data),
                   const.AUTH_CLUSTER_SIZE,
                   internal_subnets_asg,
                   external_subnets_asg,
                   [("443", "8080", "HTTPS", cert)],
                   "HTTP:8080/index.html",
                   sgs = [Ref("AuthSecurityGroup")],
                   type_=const.AUTH_TYPE,
                   depends_on=deps)
    config.add_public_dns('AuthLoadBalancer', names.public_dns('auth'))

    if USE_DB:
        config.add_rds_db("AuthDB",
                          names.auth_db.rds,
                          "3306",
                          "keycloak",
                          "keycloak",
                          "keycloak",
                          internal_subnets,
                          type_ = "db.t2.micro",
                          security_groups = [Ref("InternalSecurityGroup")])


    config.add_lambda("DNSLambda",
                      names.dns.lambda_,
                      aws.role_arn_lookup(session, 'UpdateRoute53'),
                      const.DNS_LAMBDA,
                      handler="index.handler",
                      timeout=10,
                      depends_on="DNSZone")

    config.add_lambda_permission("DNSLambdaExecute", Ref("DNSLambda"))

    config.add_sns_topic("DNSSNS",
                         names.dns.sns,
                         names.dns.sns,
                         [("lambda", Arn("DNSLambda"))])


    config.add_security_group("InternalSecurityGroup",
                              names.internal.sg,
                              [("-1", "-1", "-1", bosslet_config.NETWORK)])

    # Allow SSH access to bastion from anywhere
    incoming_subnet = bosslet_config.SSH_INBOUND
    config.add_security_group("BastionSecurityGroup",
                              names.ssh.sg,
                              [("tcp", "22", "22", incoming_subnet)])

    incoming_subnet = bosslet_config.HTTPS_INBOUND
    config.add_security_group("AuthSecurityGroup",
                              #names.https.sg, DP XXX: hack until we can get production updated correctly
                              names.auth.sg,
                              [("tcp", "443", "443", incoming_subnet)])

    # Create the internal route table to route traffic to the NAT Bastion
    all_internal_subnets = internal_subnets.copy()
    all_internal_subnets.append(Ref("InternalSubnet"))
    config.add_route_table("InternalRouteTable",
                           names.internal.rt,
                           subnets = all_internal_subnets)

    config.add_route_table_route("InternalNatRoute",
                                 Ref("InternalRouteTable"),
                                 nat = Ref("NAT"),
                                 depends_on = "NAT")

    # Create the internet gateway and internet router
    all_external_subnets = external_subnets.copy()
    all_external_subnets.append(Ref("ExternalSubnet"))
    config.add_route_table("InternetRouteTable",
                           names.internet.rt,
                           subnets = all_external_subnets)

    config.add_route_table_route("InternetRoute",
                                 Ref("InternetRouteTable"),
                                 gateway = Ref("InternetGateway"),
                                 depends_on = "AttachInternetGateway")

    config.add_internet_gateway("InternetGateway", names.internet.gw)
    config.add_endpoint("S3Endpoint", "s3", [Ref("InternalRouteTable"), Ref('InternetRouteTable')])
    config.add_endpoint("DynamoDBEndpoint", "dynamodb", [Ref("InternalRouteTable"), Ref('InternetRouteTable')])
    config.add_nat("NAT", Ref("ExternalSubnet"), depends_on="AttachInternetGateway")

    return config

def generate(bosslet_config):
    """Create the configuration and save it to disk"""
    config = create_config(bosslet_config)
    config.generate()

def pre_init(bosslet_config):
    # DP NOTE: DEPRECATED, used for transitioning public DNS records from
    #          being manually created in post-init into records that are
    #          created / managed by CloudFormation
    session = bosslet_config.session
    ext_domain = bosslet_config.EXTERNAL_DOMAIN
    names = bosslet_config.names

    console.warning("Removing existing Auth public DNS entry, so CloudFormation can manage the DNS record")
    aws.route53_delete_records(session, ext_domain, names.public_dns('auth'))

def create(bosslet_config):
    """Create the configuration, launch it, and initialize Vault"""
    config = create_config(bosslet_config)

    pre_init(bosslet_config)
    config.create()

    # NOTE: rename the default route table that is automatically created by AWS
    session = bosslet_config.session
    domain = bosslet_config.INTERNAL_DOMAIN
    vpc_id = aws.vpc_id_lookup(session, domain)
    aws.rt_name_default(session, vpc_id, "default." + domain)

    post_init(bosslet_config)

def post_init(bosslet_config):
    session = bosslet_config.session
    call = bosslet_config.call
    names = bosslet_config.names

    # OIDC Discovery URL
    auth_domain = names.public_dns("auth")
    auth_discovery_url = "https://{}/auth/realms/BOSS".format(auth_domain)

    # Generate initial user accounts
    username = "admin"
    password = utils.generate_password()
    realm_username = "bossadmin"
    realm_password = utils.generate_password()

    # Initialize Vault
    print("Waiting for Vault...")
    call.check_vault(const.TIMEOUT_VAULT)

    with call.vault() as vault:
        print("Initializing Vault...")
        try:
            vault.initialize(bosslet_config.ACCOUNT_ID)
        except Exception as ex:
            print(ex)
            print("Could not initialize Vault")
            print("Call: {}".format(utils.get_command("post-init")))
            print("Before launching other stacks")
            return False

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

        if not vault.read(const.VAULT_KEYCLOAK_DB):
            print("Writing {}".format(const.VAULT_KEYCLOAK_DB))
            # Values are hardcodded both here and in the add_rds
            # as the values are also hardcodded in the Keycloak config
            #
            # These values are for use by the backup / restore process
            vault.write(const.VAULT_KEYCLOAK_DB,
                        name = "keycloak",
                        user = "keycloak",
                        password = "keycloak")

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

    with call.ssh(names.auth.dns) as ssh:
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

    with call.tunnel(names.auth.dns, 8080) as port:
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
    instances = [ names.vault.dns ]
    scalyr.add_instances_to_scalyr(session, bosslet_config.REGION, instances)

def update(bosslet_config):
    # Checks to make sure they update can happen and the user wants to wait the required time
    if not bosslet_config.AUTH_RDS:
        print("Cannot update Auth server as it is not using an external database")
        print("Updating the Auth server would loose all Keycloak information")
        raise BossManageError("Configuration doesn't support 'update'")

    call = bosslet_config.call

    config = create_config(bosslet_config)
    transition_vault = (1,2) == (config.existing_version(), config.version())

    if transition_vault:
        if not console.confirm("This updated will recreate the Vault cluster, proceed?", default = False):
            raise BossManageCanceled()

        export_path = const.repo_path('vault', 'private', names.vault, 'export.json')
        with call.vault() as vault:
            vault_data = vault.export("secret/")
            with open(export_path, 'w') as outfile:
                json.dump(vault_data, outfile, indent=3, sort_keys=True)
                print("Vault data exported to {}".format(export_path))

    config.update(session)

    print("Waiting for Vault...")
    if not call.check_vault(90, exception=False):
        print("Could not contact Vault, check networking and run the following command")
        if transition_vault:
            print("python3 bastion.py vault.bosslet vault-init")
            print("python3 bastion.py vault.bosslet vault-import {}".format(export_path))
        else:
            print("python3 bastion.py vault.bosslet vault-status")
        print("To verify that Vault is working correctly")
        raise BossManageError("Could not contact Vault")

    if transition_vault:
        aws.route53_delete_records(session, domain, 'consul.' + bosslet_config.INTERNAL_DOMAIN)

        with call.vault() as vault:
            is_init = False
            try:
                vault.initialize()
                is_init = True
                vault.import_(vault_data)
            except Exception as ex:
                print("Problem updating Vault configuration")
                print("Run the following commands to finalize the configuration")
                if not is_init:
                    print("python3 bastion.py vault.bosslet vault-init")
                print("python3 bastion.py vault.bosslet vault-import {}".format(export_path))
                raise

    print("Stack should be ready for use")


def delete(bosslet_config):
    # NOTE: CloudWatch logs for the DNS Lambda are not deleted
    if not console.confirm("All data will be lost. Are you sure you want to proceed?"):
        raise BossManageCanceled()

    session = bosslet_config.session
    domain = bosslet_config.INTERNAL_DOMAIN
    names = bosslet_config.names

    aws.route53_delete_records(session, domain, names.auth.dns)
    aws.route53_delete_records(session, domain, names.vault.dns)

    aws.sns_unsubscribe_all(bosslet_config, names.dns.sns)

    config = CloudFormationConfiguration('core', bosslet_config)
    if config.existing_version() == 1: # Deleting a stack that has not been updated
        aws.route53_delete_records(session, domain, 'consul.' + domain)
    config.delete()


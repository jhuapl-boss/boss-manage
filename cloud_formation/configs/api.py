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
Create the api configuration which consists of
  * An endpoint web server in the external subnet
  * A RDS DB Instance launched into two new subnets (A and B)

The api configuration creates all of the resources needed to run the
BOSS system. The api configuration expects to be launched / created
in a VPC created by the core configuration. It also expects for the user to
select the same KeyPair used when creating the core configuration.
"""

from lib.cloudformation import CloudFormationConfiguration, Arg, Ref, Arn
from lib.userdata import UserData
from lib.names import AWSNames
from lib.keycloak import KeyCloakClient
from lib.external import ExternalCalls
from lib import aws
from lib import utils
from lib import scalyr
from lib import constants as const

import json
import uuid
import sys

def create_config(session, domain, keypair=None, db_config={}):
    """
    Create the CloudFormationConfiguration object.
    Args:
        session: amazon session object
        domain (string): domain of the stack being created
        keypair: keypair used to by instances being created
        db_config (dict): information needed by rds

    Returns: the config for the Cloud Formation stack

    """

    names = AWSNames(domain)

    # Lookup IAM Role and SNS Topic ARNs for used later in the config
    endpoint_role_arn = aws.role_arn_lookup(session, "endpoint")
    cachemanager_role_arn = aws.role_arn_lookup(session, 'cachemanager')
    dns_arn = aws.sns_topic_lookup(session, names.dns.replace(".", "-"))
    if dns_arn is None:
        raise Exception("SNS topic named dns." + domain + " does not exist.")

    # Configure Vault and create the user data config that the endpoint will
    # use for connecting to Vault and the DB instance
    user_data = UserData()
    user_data["system"]["fqdn"] = names.endpoint
    user_data["system"]["type"] = "endpoint"
    user_data["aws"]["db"] = names.endpoint_db
    user_data["aws"]["cache"] = names.cache
    user_data["aws"]["cache-state"] = names.cache_state

    ## cache-db and cache-stat-db need to be in user_data for lambda to access them.
    user_data["aws"]["cache-db"] = "0"
    user_data["aws"]["cache-state-db"] = "0"
    user_data["aws"]["meta-db"] = names.meta

    # Use CloudFormation's Ref function so that queues' URLs are placed into
    # the Boss config file.
    user_data["aws"]["s3-flush-queue"] = str(Ref("S3FlushQueue")) 
    user_data["aws"]["s3-flush-deadletter-queue"] = str(Ref("DeadLetterQueue"))
    user_data["aws"]["cuboid_bucket"] = names.cuboid_bucket
    user_data["aws"]["tile_bucket"] = names.tile_bucket
    user_data["aws"]["ingest_bucket"] = names.ingest_bucket
    user_data["aws"]["s3-index-table"] = names.s3_index
    user_data["aws"]["tile-index-table"] = names.tile_index
    user_data["aws"]["id-index-table"] = names.id_index
    user_data["aws"]["id-count-table"] = names.id_count_index

    user_data["auth"]["OIDC_VERIFY_SSL"] = 'True'
    user_data["lambda"]["flush_function"] = names.multi_lambda
    user_data["lambda"]["page_in_function"] = names.multi_lambda
    user_data["lambda"]["ingest_function"] = names.multi_lambda

    # Prepare user data for parsing by CloudFormation.
    parsed_user_data = { "Fn::Join" : ["", user_data.format_for_cloudformation()]}

    config = CloudFormationConfiguration('api', domain, const.REGION)

    vpc_id = config.find_vpc(session)
    az_subnets, external_subnets = config.find_all_availability_zones(session)
    sgs = aws.sg_lookup_all(session, vpc_id)

    # DP XXX: hack until we can get productio updated correctly
    config.add_security_group('AllHTTPSSecurityGroup', 'https.' + domain, [('tcp', '443', '443', '0.0.0.0/0')])
    sgs[names.https] = Ref('AllHTTPSSecurityGroup')

    # Create SQS queues and apply access control policies.
    config.add_sqs_queue("DeadLetterQueue", names.deadletter_queue, 30, 20160)

    max_receives = 3
    config.add_sqs_queue("S3FlushQueue",
                         names.s3flush_queue,
                         30,
                         dead=(Arn("DeadLetterQueue"), max_receives))

    config.add_sqs_policy("EndpointPolicy", 'sqsEndpointPolicy',
                          [Ref("DeadLetterQueue"), Ref("S3FlushQueue")],
                          endpoint_role_arn)

    config.add_sqs_policy("CachemgrPolicy", 'sqsCachemgrPolicy',
                          [Ref("DeadLetterQueue"), Ref("S3FlushQueue")],
                          cachemanager_role_arn)

    # Create the endpoint ASG, ELB, and RDS instance
    config.add_autoscale_group("Endpoint",
                               names.endpoint,
                               aws.ami_lookup(session, "endpoint.boss"),
                               keypair,
                               subnets=az_subnets,
                               type_=const.ENDPOINT_TYPE,
                               security_groups=[sgs[names.internal]],
                               user_data=parsed_user_data,
                               min=const.ENDPOINT_CLUSTER_SIZE,
                               max=const.ENDPOINT_CLUSTER_SIZE,
                               elb=Ref("EndpointLoadBalancer"),
                               notifications=dns_arn,
                               role = aws.instance_profile_arn_lookup(session, 'endpoint'),
                               health_check_grace_period=90,
                               depends_on=["EndpointLoadBalancer", "EndpointDB"])

    cert = aws.cert_arn_lookup(session, names.public_dns("api"))
    config.add_loadbalancer("EndpointLoadBalancer",
                            names.endpoint_elb,
                            [("443", "80", "HTTPS", cert)],
                            subnets=external_subnets,
                            security_groups=[sgs[names.internal], sgs[names.https]],
                            public=True)

    config.add_rds_db("EndpointDB",
                      names.endpoint_db,
                      db_config.get("port"),
                      db_config.get("name"),
                      db_config.get("user"),
                      db_config.get("password"),
                      az_subnets,
                      type_ = const.RDS_TYPE,
                      security_groups=[sgs[names.internal]])

    # Create the Meta, s3Index, tileIndex, annotation Dynamo tables
    with open(const.DYNAMO_METADATA_SCHEMA, 'r') as fh:
        dynamo_cfg = json.load(fh)
    config.add_dynamo_table_from_json("EndpointMetaDB", names.meta, **dynamo_cfg)

    with open(const.DYNAMO_S3_INDEX_SCHEMA , 'r') as s3fh:
        dynamo_s3_cfg = json.load(s3fh)
    config.add_dynamo_table_from_json('S3Index', names.s3_index, **dynamo_s3_cfg)

    with open(const.DYNAMO_TILE_INDEX_SCHEMA , 'r') as tilefh:
        dynamo_tile_cfg = json.load(tilefh)
    config.add_dynamo_table_from_json('TileIndex', names.tile_index, **dynamo_tile_cfg)

    with open(const.DYNAMO_ID_INDEX_SCHEMA , 'r') as id_ind_fh:
        dynamo_id_ind__cfg = json.load(id_ind_fh)
    config.add_dynamo_table_from_json('IdIndex', names.id_index, **dynamo_id_ind__cfg)

    with open(const.DYNAMO_ID_COUNT_SCHEMA , 'r') as id_count_fh:
        dynamo_id_count_cfg = json.load(id_count_fh)
    config.add_dynamo_table_from_json('IdCountIndex', names.id_count_index, **dynamo_id_count_cfg)

    # Create the Cache and CacheState Redis Clusters
    config.add_redis_replication("Cache",
                                 names.cache,
                                 az_subnets,
                                 [sgs[names.internal]],
                                 type_=const.REDIS_TYPE,
                                 clusters=const.REDIS_CLUSTER_SIZE)

    config.add_redis_replication("CacheState",
                                 names.cache_state,
                                 az_subnets,
                                 [sgs[names.internal]],
                                 type_=const.REDIS_TYPE,
                                 clusters=const.REDIS_CLUSTER_SIZE)

    return config


def generate(session, domain):
    """Create the configuration and save it to disk"""
    config = create_config(session, domain)
    config.generate()

def create(session, domain):
    """Configure Vault, create the configuration, and launch it"""
    keypair = aws.keypair_lookup(session)

    call = ExternalCalls(session, keypair, domain)

    db_config = const.ENDPOINT_DB_CONFIG.copy()
    db_config['password'] = utils.generate_password()

    with call.vault() as vault:
        vault.write(const.VAULT_ENDPOINT, secret_key = str(uuid.uuid4()))
        vault.write(const.VAULT_ENDPOINT_DB, **db_config)

    config = create_config(session, domain, keypair, db_config)

    try:
        success = config.create(session)
    except:
        print("Error detected, revoking secrets")
        try:
            with call.vault() as vault:
                vault.delete(const.VAULT_ENDPOINT)
                vault.delete(const.VAULT_ENDPOINT_DB)
                #vault.delete(const.VAULT_ENDPOINT_AUTH) # Deleting this will bork the whole stack
        except:
            print("Error revoking Django credentials")

        raise

    if not success:
        raise Exception("Create Failed")
    else:
        # Outside the try/except so it can be run again if there is an error
        post_init(session, domain)


def post_init(session, domain):
    # Keypair is needed by ExternalCalls
    keypair = aws.keypair_lookup(session)
    call = ExternalCalls(session, keypair, domain)
    names = AWSNames(domain)

    # Configure external DNS
    # DP ???: Can this be moved into the CloudFormation template?
    dns = names.public_dns("api")
    dns_elb = aws.elb_public_lookup(session, names.endpoint_elb)
    aws.set_domain_to_dns_name(session, dns, dns_elb, aws.get_hosted_zone(session))

    # Write data into Vault
    # DP TODO: Move into the pre-launch Vault writes, so it is available when the
    #          machines initially start
    with call.vault() as vault:
        uri = "https://{}".format(dns)
        vault.update(const.VAULT_ENDPOINT_AUTH, public_uri = uri)

        creds = vault.read("secret/auth")

    # Verify Keycloak is accessible
    print("Checking for Keycloak availability")
    call.check_keycloak(const.TIMEOUT_KEYCLOAK)

    # Add the API servers to the list of OIDC valid redirects
    with call.tunnel(names.auth, 8080) as auth_port:
        print("Update KeyCloak Client Info")
        auth_url = "http://localhost:{}".format(auth_port)
        with KeyCloakClient(auth_url, **creds) as kc:
            # DP TODO: make add_redirect_uri able to work multiple times without issue
            kc.add_redirect_uri("BOSS","endpoint", uri + "/*")

    # Tell Scalyr to get CloudWatch metrics for these instances.
    instances = [names.endpoint]
    scalyr.add_instances_to_scalyr(
        session, const.REGION, instances)

def update(session, domain):
    keypair = aws.keypair_lookup(session)

    call = ExternalCalls(session, keypair, domain)

    with call.vault() as vault:
        db_config = vault.read(const.VAULT_ENDPOINT_DB)

    config = create_config(session, domain, keypair, db_config)
    success = config.update(session)

    return success

def delete(session, domain):
    aws.sqs_delete_all(session, domain)
    aws.policy_delete_all(session, domain, '/ingest/')
    CloudFormationConfiguration('api', domain).delete(session)

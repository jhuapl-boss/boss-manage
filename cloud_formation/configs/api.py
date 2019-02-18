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
  * A API endpoint web server ASG, ELB, and RDS instance
  * DynamoDB tables for different indicies

The api configuration creates most of the resources needed to run the
BOSS system.
"""

# Redis dependency is because of Django session storage
DEPENDENCIES = ['core', 'redis'] # also depends on activities for step functions
                                 # but this forms a circular dependency

from lib.cloudformation import CloudFormationConfiguration, Arg, Ref, Arn
from lib.userdata import UserData
from lib.keycloak import KeyCloakClient
from lib.exceptions import BossManageCanceled
from lib import aws
from lib import utils
from lib import scalyr
from lib import constants as const

import json
import uuid
import sys
from urllib.request import Request, urlopen
from urllib.parse import urlencode

def create_config(bosslet_config, db_config={}):
    names = bosslet_config.names
    session = bosslet_config.session

    # Lookup IAM Role and SNS Topic ARNs for used later in the config
    endpoint_role_arn = aws.role_arn_lookup(session, "endpoint")
    cachemanager_role_arn = aws.role_arn_lookup(session, 'cachemanager')
    dns_arn = aws.sns_topic_lookup(session, names.dns.sns)
    if dns_arn is None:
        raise Exception("SNS topic named " + names.dns.sns + " does not exist.")

    mailing_list_arn = aws.sns_topic_lookup(session, const.PRODUCTION_MAILING_LIST)
    if mailing_list_arn is None:
        msg = "MailingList {} needs to be created before running config".format(const.PRODUCTION_MAILING_LIST)
        raise Exception(msg)

    # Configure Vault and create the user data config that the endpoint will
    # use for connecting to Vault and the DB instance
    user_data = UserData()
    user_data["system"]["fqdn"] = names.endpoint.dns
    user_data["system"]["type"] = "endpoint"
    user_data["aws"]["db"] = names.endpoint_db.rds
    user_data["aws"]["cache"] = names.cache.redis
    user_data["aws"]["cache-state"] = names.cache_state.redis
    if const.REDIS_SESSION_TYPE is not None:
        user_data["aws"]["cache-session"] = names.cache_session.redis
    else:
        # Don't create a Redis server for dev stacks.
        user_data["aws"]["cache-session"] = ''

    ## cache-db and cache-stat-db need to be in user_data for lambda to access them.
    user_data["aws"]["cache-db"] = "0"
    user_data["aws"]["cache-state-db"] = "0"
    user_data["aws"]["cache-session-db"] = "0"
    user_data["aws"]["meta-db"] = names.meta.ddb

    # Use CloudFormation's Ref function so that queues' URLs are placed into
    # the Boss config file.
    user_data["aws"]["s3-flush-queue"] = str(Ref(names.s3flush.sqs)) # str(Ref("S3FlushQueue")) DP XXX
    user_data["aws"]["s3-flush-deadletter-queue"] = str(Ref(names.deadletter.sqs)) #str(Ref("DeadLetterQueue")) DP XXX
    user_data["aws"]["cuboid_bucket"] = names.cuboid_bucket.s3
    user_data["aws"]["tile_bucket"] = names.tile_bucket.s3
    user_data["aws"]["ingest_bucket"] = names.ingest_bucket.s3
    user_data["aws"]["s3-index-table"] = names.s3_index.ddb
    user_data["aws"]["tile-index-table"] = names.tile_index.ddb
    user_data["aws"]["id-index-table"] = names.id_index.ddb
    user_data["aws"]["id-count-table"] = names.id_count_index.ddb
    user_data["aws"]["prod_mailing_list"] = mailing_list_arn
    user_data["aws"]["max_task_id_suffix"] = str(const.MAX_TASK_ID_SUFFIX)
    user_data["aws"]["id-index-new-chunk-threshold"] = str(const.DYNAMO_ID_INDEX_NEW_CHUNK_THRESHOLD)
    user_data["aws"]["index-deadletter-queue"] = str(Ref(names.index_deadletter.sqs))
    user_data["aws"]["index-cuboids-keys-queue"] = str(Ref(names.index_cuboids_keys.sqs))

    user_data["auth"]["OIDC_VERIFY_SSL"] = str(bosslet_config.VERIFY_SSL)
    user_data["lambda"]["flush_function"] = names.multi_lambda.lambda_
    user_data["lambda"]["page_in_function"] = names.multi_lambda.lambda_
    user_data["lambda"]["ingest_function"] = names.tile_ingest.lambda_
    user_data["lambda"]["downsample_volume"] = names.downsample_volume.lambda_

    user_data['sfn']['populate_upload_queue'] = names.ingest_queue_populate.sfn
    user_data['sfn']['upload_sfn'] = names.ingest_queue_upload.sfn
    user_data['sfn']['downsample_sfn'] = names.resolution_hierarchy.sfn
    user_data['sfn']['index_id_writer_sfn'] = names.index_id_writer.sfn
    user_data['sfn']['index_cuboid_supervisor_sfn'] = names.index_cuboid_supervisor.sfn

    # Prepare user data for parsing by CloudFormation.
    parsed_user_data = { "Fn::Join" : ["", user_data.format_for_cloudformation()]}

    config = CloudFormationConfiguration('api', bosslet_config)
    keypair = bosslet_config.SSH_KEY

    vpc_id = config.find_vpc()
    internal_subnets, external_subnets = config.find_all_subnets()
    az_subnets_asg, external_subnets_asg = config.find_all_subnets(compatibility='asg')
    sgs = aws.sg_lookup_all(session, vpc_id)

    # DP XXX: hack until we can get productio updated correctly
    config.add_security_group('AllHTTPSSecurityGroup', names.https.sg, [('tcp', '443', '443', bosslet_config.HTTPS_INBOUND)])
    sgs[names.https.sg] = Ref('AllHTTPSSecurityGroup')


    # Create SQS queues and apply access control policies.
    # Deadletter queue for indexing operations.  This one is populated
    # manually by states in the indexing step functions.
    config.add_sqs_queue(names.index_deadletter.sqs, names.index_deadletter.sqs, 30, 20160)

    # Queue that holds S3 object keys of cuboids to be indexed.
    config.add_sqs_queue(names.index_cuboids_keys.sqs, names.index_cuboids_keys.sqs, 120, 20160)

    #config.add_sqs_queue("DeadLetterQueue", names.deadletter.sqs, 30, 20160) DP XXX
    config.add_sqs_queue(names.deadletter.sqs, names.deadletter.sqs, 30, 20160)

    max_receives = 3
    #config.add_sqs_queue("S3FlushQueue", DP XXX
    config.add_sqs_queue(names.s3flush.sqs,
                         names.s3flush.sqs,
                         30,
                         dead=(Arn(names.deadletter.sqs), max_receives))

    config.add_sqs_policy("sqsEndpointPolicy", 'sqsEndpointPolicy', # DP XXX
                          [Ref(names.deadletter.sqs), Ref(names.s3flush.sqs)],
                          endpoint_role_arn)

    config.add_sqs_policy("sqsCachemgrPolicy", 'sqsCachemgrPolicy', # DP XXX
                          [Ref(names.deadletter.sqs), Ref(names.s3flush.sqs)],
                          cachemanager_role_arn)

    # Create the endpoint ASG, ELB, and RDS instance
    config.add_autoscale_group("Endpoint",
                               names.endpoint.dns,
                               aws.ami_lookup(bosslet_config, names.endpoint.ami),
                               keypair,
                               subnets=az_subnets_asg,
                               type_=const.ENDPOINT_TYPE,
                               security_groups=[sgs[names.internal.sg]],
                               user_data=parsed_user_data,
                               min=const.ENDPOINT_CLUSTER_MIN,
                               max=const.ENDPOINT_CLUSTER_MAX,
                               elb=Ref("EndpointLoadBalancer"),
                               notifications=dns_arn,
                               role=aws.instance_profile_arn_lookup(session, 'endpoint'),
                               health_check_grace_period=90,
                               detailed_monitoring=True,
                               depends_on=["EndpointLoadBalancer", "EndpointDB"])

    cert = aws.cert_arn_lookup(session, names.public_dns("api"))
    config.add_loadbalancer("EndpointLoadBalancer",
                            names.endpoint_elb.dns,
                            [("443", "80", "HTTPS", cert)],
                            subnets=external_subnets_asg,
                            security_groups=[sgs[names.internal.sg], sgs[names.https.sg]],
                            public=True)

    # Endpoint servers are not CPU bound typically, so react quickly to load
    config.add_autoscale_policy("EndpointScaleUp",
                                Ref("Endpoint"),
                                adjustments=[
                                    (0.0, 10, 1),  # 12% - 22% Utilization add 1 instance
                                    (10, None, 2)  # Above 22% Utilization add 2 instances
                                ],
                                alarms=[
                                    ("CPUUtilization", "Maximum", "GreaterThanThreshold", "12")
                                ],
                                period=1)

    config.add_autoscale_policy("EndpointScaleDown",
                                Ref("Endpoint"),
                                adjustments=[
                                    (None, 0.0, -1),   # Under 1.5% Utilization remove 1 instance
                                ],
                                alarms=[
                                    ("CPUUtilization", "Average", "LessThanThreshold", "1.5")
                                ],
                                period=50)

    config.add_rds_db("EndpointDB",
                      names.endpoint_db.dns,
                      db_config.get("port"),
                      db_config.get("name"),
                      db_config.get("user"),
                      db_config.get("password"),
                      internal_subnets,
                      type_ = const.RDS_TYPE,
                      security_groups=[sgs[names.internal.sg]])

    # Create the Meta, s3Index, tileIndex, annotation Dynamo tables
    with open(const.DYNAMO_METADATA_SCHEMA, 'r') as fh:
        dynamo_cfg = json.load(fh)
    config.add_dynamo_table_from_json("EndpointMetaDB", names.meta.ddb, **dynamo_cfg)

    with open(const.DYNAMO_S3_INDEX_SCHEMA, 'r') as s3fh:
        dynamo_s3_cfg = json.load(s3fh)
    config.add_dynamo_table_from_json('s3Index', names.s3_index.ddb, **dynamo_s3_cfg)  # DP XXX

    with open(const.DYNAMO_TILE_INDEX_SCHEMA, 'r') as tilefh:
        dynamo_tile_cfg = json.load(tilefh)
    config.add_dynamo_table_from_json('tileIndex', names.tile_index.ddb, **dynamo_tile_cfg)  # DP XXX

    with open(const.DYNAMO_ID_INDEX_SCHEMA, 'r') as id_ind_fh:
        dynamo_id_ind__cfg = json.load(id_ind_fh)
    config.add_dynamo_table_from_json('idIndIndex', names.id_index.ddb, **dynamo_id_ind__cfg)  # DP XXX

    with open(const.DYNAMO_ID_COUNT_SCHEMA, 'r') as id_count_fh:
        dynamo_id_count_cfg = json.load(id_count_fh)
    config.add_dynamo_table_from_json('idCountIndex', names.id_count_index.ddb, **dynamo_id_count_cfg)  # DP XXX

    return config


def generate(bosslet_config):
    """Create the configuration and save it to disk"""
    try:
        with bosslet_config.call.vault() as vault:
            db_config = vault.read(const.VAULT_ENDPOINT_DB)
            if db_config is None:
                raise Exception()
    except:
        db_config = const.ENDPOINT_DB_CONFIG.copy()

    config = create_config(bosslet_config, db_config)
    config.generate()

def create(bosslet_config):
    """Configure Vault, create the configuration, and launch it"""
    db_config = const.ENDPOINT_DB_CONFIG.copy()
    db_config['password'] = utils.generate_password()

    with bosslet_config.call.vault() as vault:
        vault.write(const.VAULT_ENDPOINT, secret_key = str(uuid.uuid4()))
        vault.write(const.VAULT_ENDPOINT_DB, **db_config)

        dns = bosslet_config.names.public_dns("api")
        uri = "https://{}".format(dns)
        vault.update(const.VAULT_ENDPOINT_AUTH, public_uri = uri)

    config = create_config(bosslet_config, db_config)

    try:
        config.create()
    except:
        print("Error detected, revoking secrets")
        try:
            with bosslet_config.call.vault() as vault:
                vault.delete(const.VAULT_ENDPOINT)
                vault.delete(const.VAULT_ENDPOINT_DB)
                #vault.delete(const.VAULT_ENDPOINT_AUTH) # Deleting this will bork the whole stack
        except:
            print("Error revoking Django credentials")

        raise

    # Outside the try/except so it can be run again if there is an error
    post_init(bosslet_config)

def post_init(bosslet_config):
    session = bosslet_config.session
    call = bosslet_config.call
    names = bosslet_config.names

    # Configure external DNS
    # DP ???: Can this be moved into the CloudFormation template?
    dns = names.public_dns("api")
    dns_elb = aws.elb_public_lookup(session, names.endpoint_elb.dns)
    hosted_zone = bosslet_config.EXTERNAL_DOMAIN
    aws.set_domain_to_dns_name(session, dns, dns_elb, hosted_zone)

    # Write data into Vault
    # DP TODO: Move into the pre-launch Vault writes, so it is available when the
    #          machines initially start
    with call.vault() as vault:
        uri = "https://{}".format(dns)
        #vault.update(const.VAULT_ENDPOINT_AUTH, public_uri = uri)

        creds = vault.read("secret/auth")
        bossadmin = vault.read("secret/auth/realm")
        auth_uri = vault.read("secret/endpoint/auth")['url']

    # Verify Keycloak is accessible
    print("Checking for Keycloak availability")
    call.check_keycloak(const.TIMEOUT_KEYCLOAK)

    # Add the API servers to the list of OIDC valid redirects
    with call.tunnel(names.auth.dns, 8080) as auth_port:
        print("Update KeyCloak Client Info")
        auth_url = "http://localhost:{}".format(auth_port)
        with KeyCloakClient(auth_url, **creds) as kc:
            # DP TODO: make add_redirect_uri able to work multiple times without issue
            kc.add_redirect_uri("BOSS","endpoint", uri + "/*")

    # Get the boss admin's bearer token
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    params = {
        'grant_type': 'password',
        'client_id': bossadmin['client_id'],
        'username': bossadmin['username'],
        'password': bossadmin['password'],
    }

    auth_uri += '/protocol/openid-connect/token'
    req = Request(auth_uri,
                  headers = headers,
                  data = urlencode(params).encode('utf-8'))
    resp = json.loads(urlopen(req).read().decode('utf-8'))

    # Make an API call that will log the boss admin into the endpoint
    call.check_url(uri + '/ping', 60)
    headers = {
        'Authorization': 'Bearer {}'.format(resp['access_token']),
    }
    api_uri = uri + '/latest/collection'
    req = Request(api_uri, headers = headers)
    resp = json.loads(urlopen(req).read().decode('utf-8'))
    print("Collections: {}".format(resp))

    # Tell Scalyr to get CloudWatch metrics for these instances.
    instances = [names.endpoint.dns]
    scalyr.add_instances_to_scalyr(
        session, bosslet_config.REGION, instances)

def update(bosslet_config):
    with bosslet_config.call.vault() as vault:
        db_config = vault.read(const.VAULT_ENDPOINT_DB)

    config = create_config(bosslet_config, db_config)
    config.update()

def delete(bosslet_config):
    session = bosslet_config.session
    domain = bosslet_config.INTERNAL_DOMAIN
    names = bosslet_config.names

    if not utils.get_user_confirm("All data will be lost. Are you sure you want to proceed?"):
        raise BossManageCanceled()

    aws.route53_delete_records(session, domain, names.endpoint.dns)
    # Other configs may define SQS queues and we shouldn't delete them
    aws.sqs_delete_all(session, domain) # !!! TODO FIX this so it doesn't bork the stack
    aws.policy_delete_all(session, domain, '/ingest/')

    config = CloudFormationConfiguration('api', bosslet_config)
    config.delete()

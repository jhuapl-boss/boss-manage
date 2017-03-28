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
from lib.cloudformation import get_scenario

import json
import uuid
import sys
from urllib.request import Request, urlopen
from urllib.parse import urlencode

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

    mailing_list_arn = aws.sns_topic_lookup(session, const.PRODUCTION_MAILING_LIST)
    if mailing_list_arn is None:
        msg = "MailingList {} needs to be created before running config".format(const.PRODUCTION_MAILING_LIST)
        raise Exception(msg)

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
    user_data["aws"]["s3-flush-queue"] = str(Ref(names.s3flush_queue)) # str(Ref("S3FlushQueue")) DP XXX
    user_data["aws"]["s3-flush-deadletter-queue"] = str(Ref(names.deadletter_queue)) #str(Ref("DeadLetterQueue")) DP XXX
    user_data["aws"]["cuboid_bucket"] = names.cuboid_bucket
    user_data["aws"]["tile_bucket"] = names.tile_bucket
    user_data["aws"]["ingest_bucket"] = names.ingest_bucket
    user_data["aws"]["s3-index-table"] = names.s3_index
    user_data["aws"]["tile-index-table"] = names.tile_index
    user_data["aws"]["id-index-table"] = names.id_index
    user_data["aws"]["id-count-table"] = names.id_count_index
    user_data["aws"]["prod_mailing_list"] = mailing_list_arn

    user_data["auth"]["OIDC_VERIFY_SSL"] = 'True'
    user_data["lambda"]["flush_function"] = names.multi_lambda
    user_data["lambda"]["page_in_function"] = names.multi_lambda
    user_data["lambda"]["ingest_function"] = names.multi_lambda

    user_data['sfn']['populate_upload_queue'] = names.ingest_queue_populate
    user_data['sfn']['upload_sfn'] = names.ingest_queue_upload

    # Prepare user data for parsing by CloudFormation.
    parsed_user_data = { "Fn::Join" : ["", user_data.format_for_cloudformation()]}

    config = CloudFormationConfiguration('api', domain, const.REGION)

    vpc_id = config.find_vpc(session)
    az_subnets, external_subnets = config.find_all_availability_zones(session)
    az_subnets_lambda, external_subnets_lambda = config.find_all_availability_zones(session, lambda_compatible_only=True)
    sgs = aws.sg_lookup_all(session, vpc_id)

    # DP XXX: hack until we can get productio updated correctly
    config.add_security_group('AllHTTPSSecurityGroup', 'https.' + domain, [('tcp', '443', '443', '0.0.0.0/0')])
    sgs[names.https] = Ref('AllHTTPSSecurityGroup')

    # Create SQS queues and apply access control policies.
    #config.add_sqs_queue("DeadLetterQueue", names.deadletter_queue, 30, 20160) DP XXX
    config.add_sqs_queue(names.deadletter_queue, names.deadletter_queue, 30, 20160)

    max_receives = 3
    #config.add_sqs_queue("S3FlushQueue", DP XXX
    config.add_sqs_queue(names.s3flush_queue,
                         names.s3flush_queue,
                         30,
                         dead=(Arn(names.deadletter_queue), max_receives))

    config.add_sqs_policy("sqsEndpointPolicy", 'sqsEndpointPolicy', # DP XXX
                          [Ref(names.deadletter_queue), Ref(names.s3flush_queue)],
                          endpoint_role_arn)

    config.add_sqs_policy("sqsCachemgrPolicy", 'sqsCachemgrPolicy', # DP XXX
                          [Ref(names.deadletter_queue), Ref(names.s3flush_queue)],
                          cachemanager_role_arn)

    # Create the endpoint ASG, ELB, and RDS instance
    config.add_autoscale_group("Endpoint",
                               names.endpoint,
                               aws.ami_lookup(session, "endpoint.boss"),
                               keypair,
                               subnets=az_subnets_lambda,
                               type_=const.ENDPOINT_TYPE,
                               security_groups=[sgs[names.internal]],
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
                            names.endpoint_elb,
                            [("443", "80", "HTTPS", cert)],
                            subnets=external_subnets_lambda,
                            security_groups=[sgs[names.internal], sgs[names.https]],
                            public=True)

    # Endpoint servers are not CPU bound typically, so react quickly to load
    config.add_autoscale_policy("EndpointScaleUp",
                                Ref("Endpoint"),
                                adjustments=[
                                    (0.0, 0.10, 1),  # 10% - 20% Utilization add 1 instance
                                    (0.20, None, 2)  # Above 20% Utilization add 2 instances
                                ],
                                alarms=[
                                    ("CPUUtilization ", "Average", "GreaterThanThreshold", "0.10")
                                ],
                                period=1)

    config.add_autoscale_policy("EndpointScaleDown",
                                Ref("Endpoint"),
                                adjustments=[
                                    (None, 0.0, 1),   # Under 1% Utilization remove 1 instance
                                ],
                                alarms=[
                                    ("CPUUtilization ", "Average", "LessThanThreshold", "0.01")
                                ],
                                period=5)

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
    config.add_dynamo_table_from_json('s3Index', names.s3_index, **dynamo_s3_cfg)  # DP XXX

    with open(const.DYNAMO_TILE_INDEX_SCHEMA , 'r') as tilefh:
        dynamo_tile_cfg = json.load(tilefh)
    config.add_dynamo_table_from_json('tileIndex', names.tile_index, **dynamo_tile_cfg)  # DP XXX

    with open(const.DYNAMO_ID_INDEX_SCHEMA , 'r') as id_ind_fh:
        dynamo_id_ind__cfg = json.load(id_ind_fh)
    config.add_dynamo_table_from_json('idIndIndex', names.id_index, **dynamo_id_ind__cfg)  # DP XXX

    with open(const.DYNAMO_ID_COUNT_SCHEMA , 'r') as id_count_fh:
        dynamo_id_count_cfg = json.load(id_count_fh)
    config.add_dynamo_table_from_json('idCountIndex', names.id_count_index, **dynamo_id_count_cfg)  # DP XXX

    # Create the Cache and CacheState Redis Clusters
    REDIS_PARAMETERS = {
        "maxmemory-policy": "volatile-lru",
        "reserved-memory": str(get_scenario(const.REDIS_RESERVED_MEMORY, 0) * 1000000),
        "maxmemory-samples": "5", # ~ 5 - 10
    }

    config.add_redis_replication("Cache",
                                 names.cache,
                                 az_subnets,
                                 [sgs[names.internal]],
                                 type_=const.REDIS_CACHE_TYPE,
                                 version="3.2.4",
                                 clusters=const.REDIS_CLUSTER_SIZE,
                                 parameters=REDIS_PARAMETERS)

    config.add_redis_replication("CacheState",
                                 names.cache_state,
                                 az_subnets,
                                 [sgs[names.internal]],
                                 type_=const.REDIS_TYPE,
                                 version="3.2.4",
                                 clusters=const.REDIS_CLUSTER_SIZE)

    return config


def generate(session, domain):
    """Create the configuration and save it to disk"""
    keypair = aws.keypair_lookup(session)

    call = ExternalCalls(session, keypair, domain)

    with call.vault() as vault:
        db_config = vault.read(const.VAULT_ENDPOINT_DB)
        if db_config is None:
            db_config = const.ENDPOINT_DB_CONFIG.copy()

    config = create_config(session, domain, keypair, db_config)
    config.generate()


def create(session, domain):
    """Configure Vault, create the configuration, and launch it"""
    keypair = aws.keypair_lookup(session)

    call = ExternalCalls(session, keypair, domain)
    names = AWSNames(domain)

    db_config = const.ENDPOINT_DB_CONFIG.copy()
    db_config['password'] = utils.generate_password()

    with call.vault() as vault:
        vault.write(const.VAULT_ENDPOINT, secret_key = str(uuid.uuid4()))
        vault.write(const.VAULT_ENDPOINT_DB, **db_config)

        dns = names.public_dns("api")
        uri = "https://{}".format(dns)
        vault.update(const.VAULT_ENDPOINT_AUTH, public_uri = uri)

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
        #vault.update(const.VAULT_ENDPOINT_AUTH, public_uri = uri)

        creds = vault.read("secret/auth")
        bossadmin = vault.read("secret/auth/realm")
        auth_uri = vault.read("secret/endpoint/auth")['url']

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
    api_uri = uri + '/v0.8/collection' # DP TODO: implement /latest for version
    req = Request(api_uri, headers = headers)
    resp = json.loads(urlopen(req).read().decode('utf-8'))
    print("Collections: {}".format(resp))

    # Tell Scalyr to get CloudWatch metrics for these instances.
    instances = [names.endpoint]
    scalyr.add_instances_to_scalyr(
        session, const.REGION, instances)

def update(session, domain):
    keypair = aws.keypair_lookup(session)
    names = AWSNames(domain)

    call = ExternalCalls(session, keypair, domain)

    with call.vault() as vault:
        db_config = vault.read(const.VAULT_ENDPOINT_DB)

    '''
    try:
        import MySQLdb as mysql
    except:
        print("Cannot save data before migrating schema, exiting...")
        return

    print("Saving time step data")
    print("Tunneling")
    with call.tunnel(names.endpoint_db, db_config['port'], type_='rds') as local_port:
        print("Connecting to MySQL")
        db = mysql.connect(host = '127.0.0.1',
                           port = local_port,
                           user = db_config['user'],
                           passwd = db_config['password'],
                           db = db_config['name'])
        cur = db.cursor()

        try:
            sql = "DROP TABLE temp_time_step"
            cur.execute(sql)
        except Exception as e:
            #print(e)
            pass # Table doesn't exist

        print("Saving Data")
        sql = """CREATE TABLE temp_time_step(time_step_unit VARCHAR(100), exp_id INT(11), coord_frame_id INT(11), time_step INT(11))
                 SELECT coordinate_frame.time_step_unit, experiment.id as exp_id, coord_frame_id, time_step
                 FROM experiment, coordinate_frame
                 WHERE coordinate_frame.id = experiment.coord_frame_id """
        cur.execute(sql)

        sql = "SELECT * FROM temp_time_step"
        cur.execute(sql)
        rows = cur.fetchall()
        print("Saved {} rows of data".format(len(rows)))
        #for r in rows:
        #    print(r)

        cur.close()
        db.close()
    '''

    config = create_config(session, domain, keypair, db_config)
    success = config.update(session)

    '''
    print("Restoring time step data")
    print("Tunneling")
    with call.tunnel(names.endpoint_db, db_config['port'], type_='rds') as local_port:
        print("Connecting to MySQL")
        db = mysql.connect(host = '127.0.0.1',
                           port = local_port,
                           user = db_config['user'],
                           passwd = db_config['password'],
                           db = db_config['name'])
        cur = db.cursor()

        if success:
            sql = """UPDATE experiment, temp_time_step
                     SET experiment.time_step_unit = temp_time_step.time_step_unit,
                         experiment.time_step = temp_time_step.time_step
                     WHERE  experiment.id = temp_time_step.exp_id AND
                            experiment.coord_frame_id = temp_time_step.coord_frame_id"""
            cur.execute(sql)
            db.commit()

            sql = "SELECT time_step_unit, id, coord_frame_id, time_step FROM experiment"
            cur.execute(sql)
            rows = cur.fetchall()
            print("Migrated {} rows of data".format(len(rows)))
            #for r in rows:
            #    print(r)
        else:
            if success is None:
                print("Update canceled, not migrating data")
            else:
                print("Error during update, not migrating data")

        print("Deleting temp table")
        sql = "DROP TABLE temp_time_step"
        cur.execute(sql)

        cur.close()
        db.close()
    '''


    return success

def delete(session, domain):
    names = AWSNames(domain)
    aws.route53_delete_records(session, domain, names.endpoint)
    aws.sqs_delete_all(session, domain)
    aws.policy_delete_all(session, domain, '/ingest/')
    CloudFormationConfiguration('api', domain).delete(session)

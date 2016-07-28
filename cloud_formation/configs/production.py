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
Create the production configuration which consists of
  * An endpoint web server in the external subnet
  * A RDS DB Instance launched into two new subnets (A and B)

The production configuration creates all of the resources needed to run the
BOSS system. The production configuration expects to be launched / created
in a VPC created by the core configuration. It also expects for the user to
select the same KeyPair used when creating the core configuration.
"""


import configuration
import library as lib
import hosts
import json
import scalyr
import uuid
import sys

# Region production is created in.  Later versions of boto3 should allow us to
# extract this from the session variable.  Hard coding for now.
PRODUCTION_REGION = 'us-east-1'

DYNAMO_SCHEMA = '../salt_stack/salt/boss/files/boss.git/django/bosscore/dynamo_schema.json'

INCOMING_SUBNET = "52.3.13.189/32"  # microns-bastion elastic IP

VAULT_DJANGO = "secret/endpoint/django"
VAULT_DJANGO_DB = "secret/endpoint/django/db"
VAULT_DJANGO_AUTH = "secret/endpoint/auth"

ENDPONT_TYPE = {
    "development": "t2.micro",
    "production": "m4.large",
}

RDS_TYPE = {
    "development": "db.t2.micro",
    "production": "db.t2.medium",
}

REDIS_TYPE = {
    "development": "cache.t2.small",
    "production": "cache.m3.xlarge",
}

REDIS_CLUSTER_SIZE = {
    "development": 1,
    "production": 2,
}

# Prefixes uses to generate names of SQS queues.
S3FLUSH_QUEUE_PREFIX = 'S3flush.'
DEADLETTER_QUEUE_PREFIX = 'Deadletter.'


def create_config(session, domain, keypair=None, user_data=None, db_config={}):
    """
    Create the CloudFormationConfiguration object.
    Args:
        session: amazon session object
        domain (string): domain of the stack being created
        keypair: keypair used to by instances being created
        user_data (configuration.UserData): information used by the endpoint instance and vault.  Data will be run through the CloudFormation Fn::Join template intrinsic function so other template intrinsic functions used in the user_data will be parsed and executed.
        db_config (dict): information needed by rds

    Returns: the config for the Cloud Formation stack

    """

    # Prepare user data for parsing by CloudFormation.
    parsed_user_data = { "Fn::Join" : ["", user_data.format_for_cloudformation()]}

    config = configuration.CloudFormationConfiguration(domain, PRODUCTION_REGION)

    # do a couple of verification checks
    if config.subnet_domain is not None:
        raise Exception("Invalid VPC domain name")

    vpc_id = lib.vpc_id_lookup(session, domain)
    if session is not None and vpc_id is None:
        raise Exception("VPC does not exists, exiting...")

    # Lookup the VPC, External Subnet, Internal Security Group IDs that are
    # needed by other resources
    config.add_arg(configuration.Arg.VPC("VPC", vpc_id,
                                         "ID of VPC to create resources in"))

    external_subnet_id = lib.subnet_id_lookup(session, "external." + domain)
    config.add_arg(configuration.Arg.Subnet("ExternalSubnet",
                                            external_subnet_id,
                                            "ID of External Subnet to create resources in"))

    internal_subnet_id = lib.subnet_id_lookup(session, "internal." + domain)
    config.add_arg(configuration.Arg.Subnet("InternalSubnet",
                                            internal_subnet_id,
                                            "ID of Internal Subnet to create resources in"))

    internal_sg_id = lib.sg_lookup(session, vpc_id, "internal." + domain)
    config.add_arg(configuration.Arg.SecurityGroup("InternalSecurityGroup",
                                                   internal_sg_id,
                                                   "ID of internal Security Group"))

    az_subnets, external_subnets = config.find_all_availability_zones(session)

    if domain in hosts.BASE_DOMAIN_CERTS.keys():
        cert = lib.cert_arn_lookup(session, "api." + hosts.BASE_DOMAIN_CERTS[domain])
    else:
        # default to using api.theboss.io
        cert = lib.cert_arn_lookup(session, "api.theboss.io")

    # Create SQS queues and apply access control policies.
    deadqname = lib.domain_to_stackname(DEADLETTER_QUEUE_PREFIX + domain)
    config.add_sqs_queue(deadqname, deadqname, 30, 20160)

    s3flushqname = lib.domain_to_stackname(S3FLUSH_QUEUE_PREFIX + domain)
    max_receives = 3
    deadq_arn = { 'Fn::GetAtt': [deadqname, 'Arn'] }
    config.add_sqs_queue(
        s3flushqname, s3flushqname, 30, dead=(deadq_arn, max_receives))

    endpoint_role_arn = 'arn:aws:iam::256215146792:role/endpoint'
    config.add_sqs_policy(
        'sqsEndpointPolicy', 'sqsEndpointPolicy', 
        [{'Ref': deadqname}, {'Ref': s3flushqname}],
        endpoint_role_arn)

    cachemanager_role_arn = 'arn:aws:iam::256215146792:role/cachemanager'
    config.add_sqs_policy(
        'sqsCachemgrPolicy', 'sqsCachemgrPolicy', 
        [{'Ref': deadqname}, {'Ref': s3flushqname}],
        cachemanager_role_arn)

    config.add_loadbalancer("LoadBalancer",
                            "elb." + domain,
                            [("443", "80", "HTTPS", cert)],
                            ["Endpoint"],
                            subnets=external_subnets,
                            security_groups=["AllHTTPSSecurityGroup"],
                            depends_on=["AllHTTPSSecurityGroup"])

    config.add_ec2_instance("Endpoint",
                            "endpoint." + domain,
                            lib.ami_lookup(session, "endpoint.boss"),
                            keypair,
                            subnet="ExternalSubnet",
                            public_ip=True,
                            type_=ENDPONT_TYPE,
                            security_groups=["InternalSecurityGroup"],
                            user_data=parsed_user_data,
                            role="endpoint",
                            depends_on="EndpointDB") # make sure the DB is launched before we start

    config.add_rds_db("EndpointDB",
                      "endpoint-db." + domain,
                      db_config.get("port"),
                      db_config.get("name"),
                      db_config.get("user"),
                      db_config.get("password"),
                      az_subnets,
                      type_ = RDS_TYPE,
                      security_groups=["InternalSecurityGroup"])

    with open(DYNAMO_SCHEMA, 'r') as fh:
        dynamo_cfg = json.load(fh)
    config.add_dynamo_table_from_json("EndpointMetaDB",'bossmeta.' + domain, **dynamo_cfg)

    config.add_redis_replication("Cache",
                                 "cache." + domain,
                                 az_subnets,
                                 ["InternalSecurityGroup"],
                                 type_=REDIS_TYPE,
                                 clusters=REDIS_CLUSTER_SIZE)
    config.add_redis_replication("CacheState",
                                 "cache-state." + domain,
                                 az_subnets,
                                 ["InternalSecurityGroup"],
                                 type_=REDIS_TYPE,
                                 clusters=REDIS_CLUSTER_SIZE)

    # Allow HTTPS access to endpoint loadbalancer from anywhere
    config.add_security_group("AllHTTPSSecurityGroup",
                              "https",
                              [("tcp", "443", "443", "0.0.0.0/0")])

    return config


def generate(folder, domain):
    """Create the configuration and save it to disk"""
    name = lib.domain_to_stackname("production." + domain)
    config = create_config(None, domain)
    config.generate(name, folder)


def create(session, domain):
    """Configure Vault, create the configuration, and launch it"""
    keypair = lib.keypair_lookup(session)

    call = lib.ExternalCalls(session, keypair, domain)

    db = {
        "name":"boss",
        "user":"testuser",
        "password": lib.generate_password(),
        "port": "3306"
    }

    s3flushqname = lib.domain_to_stackname(S3FLUSH_QUEUE_PREFIX + domain)
    deadqname = lib.domain_to_stackname(DEADLETTER_QUEUE_PREFIX + domain)

    # Configure Vault and create the user data config that the endpoint will
    # use for connecting to Vault and the DB instance
    endpoint_token = call.vault("vault-provision", "endpoint")
    user_data = configuration.UserData()
    user_data["vault"]["token"] = endpoint_token
    user_data["system"]["fqdn"] = "endpoint." + domain
    user_data["system"]["type"] = "endpoint"
    user_data["aws"]["db"] = "endpoint-db." + domain
    user_data["aws"]["cache"] = "cache." + domain
    user_data["aws"]["cache-state"] = "cache-state." + domain
    user_data["aws"]["cache-db"] = 0  ## cache-db and cache-stat-db need to be in user_data for lambda to access them.
    user_data["aws"]["cache-state-db"] = 0
    user_data["aws"]["meta-db"] = "bossmeta." + domain
    # Use CloudFormation's Ref function so that queues' URLs are placed into
    # the Boss config file.
    user_data["aws"]["s3-flush-queue"] = '{{"Ref": "{}" }}'.format(s3flushqname)
    user_data["aws"]["s3-flush-deadletter-queue"] = '{{"Ref": "{}" }}'.format(deadqname)
    user_data["auth"]["OIDC_VERIFY_SSL"] = str(domain in hosts.BASE_DOMAIN_CERTS.keys())

    call.vault_write(VAULT_DJANGO, secret_key = str(uuid.uuid4()))
    call.vault_write(VAULT_DJANGO_DB, **db)

    try:
        name = lib.domain_to_stackname("production." + domain)
        config = create_config(session, domain, keypair, user_data, db)

        success = config.create(session, name)
        if not success:
            raise Exception("Create Failed")
        else:
            post_init(session, domain)
    except:
        print("Error detected, revoking secrets") # Do we want to revoke if an exception from post_init?
        try:
            call.vault_delete(VAULT_DJANGO)
            call.vault_delete(VAULT_DJANGO_DB)
        except:
            print("Error revoking Django credentials")
        try:
            call.vault("vault-revoke", endpoint_token)
        except:
            print("Error revoking Endpoint Server Vault access token")
        raise


def post_init(session, domain):
    keypair = lib.keypair_lookup(session)
    call = lib.ExternalCalls(session, keypair, domain)

    print("Configuring KeyCloak")  # Should abstract for production and proofreader

    def configure_auth(auth_port):
        # NOTE DP: If an ELB is created the public_uri should be the Public DNS Name
        #          of the ELB. Endpoint Django instances may have to be restarted if running.
        dns = lib.elb_public_lookup(session, "elb." + domain)
        if domain in hosts.BASE_DOMAIN_CERTS.keys():
            dns_elb = dns
            dns = "api." + hosts.BASE_DOMAIN_CERTS[domain]
            lib.set_domain_to_dns_name(session, dns, dns_elb)
        uri = "https://{}".format(dns)
        call.vault_update(VAULT_DJANGO_AUTH, public_uri = uri)

        print("Update KeyCloak Client Info")
        creds = call.vault_read("secret/auth")
        kc = lib.KeyCloakClient("http://localhost:{}".format(auth_port))
        kc.login(creds["username"], creds["password"])

        kc.add_redirect_uri("BOSS","endpoint", uri + "/*")
        kc.logout()
    call.set_ssh_target("auth")
    call.ssh_tunnel(configure_auth, 8080)

    print("Initializing Django")  # Should create ssh call with array of commands
    call.set_ssh_target("endpoint")
    migrate_cmd = "sudo python3 /srv/www/django/manage.py "
    call.ssh(migrate_cmd + "makemigrations")  #
    call.ssh(migrate_cmd + "makemigrations bosscore")  # will hang if it cannot contact the auth server
    call.ssh(migrate_cmd + "migrate")
    call.ssh(migrate_cmd + "collectstatic --no-input")
    # http://stackoverflow.com/questions/6244382/how-to-automate-createsuperuser-on-django
    # For how it is possible to script createsuperuser command
    call.ssh("sudo service uwsgi-emperor reload")
    call.ssh("sudo service nginx restart")

    # Tell Scalyr to get CloudWatch metrics for these instances.
    instances = ["endpoint." + domain]
    scalyr.add_instances_to_scalyr(
        session, PRODUCTION_REGION, instances)

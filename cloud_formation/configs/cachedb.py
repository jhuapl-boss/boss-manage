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
Create the cachedb configuration which consists of

  * An cachmanager server to run three daemons for
        * cache-write
        * cache-miss
        * cache-delayed write
  * Lambdas
  * SNS topics
  * SQS queues

This will most likely be merged into production once it is finished.

"""


import configuration
import library as lib
import hosts
import json
import scalyr
import uuid
from update_lambda_fcn import load_lambdas_on_s3
import names


# Region production is created in.  Later versions of boto3 should allow us to
# extract this from the session variable.  Hard coding for now.
PRODUCTION_REGION = 'us-east-1'

INCOMING_SUBNET = "52.3.13.189/32"  # microns-bastion elastic IP

CACHE_MANAGER_TYPE = {
    "development": "t2.micro",
    "production": "t2.medium",
}

# Prefixes uses to generate names of SQS queues.
S3FLUSH_QUEUE_PREFIX = 'S3flush.'
DEADLETTER_QUEUE_PREFIX = 'Deadletter.'

WRITE_LOCK_SNS_PREFIX = 'WriteLockAlert'


def create_config(session, domain, keypair=None, user_data=None):
    """
    Create the CloudFormationConfiguration object.
    Args:
        session: amazon session object
        domain: domain of the stack being created
        keypair: keypair used to by instances being created
        user_data (configuration.UserData): information used by the endpoint instance and vault.  Data will be run through the CloudFormation Fn::Join template intrinsic function so other template intrinsic functions used in the user_data will be parsed and executed.
        db_config: information needed by rds

    Returns: the config for the Cloud Formation stack

    """

    # Prepare user data for parsing by CloudFormation.
    if user_data is not None:
        parsed_user_data = { "Fn::Join" : ["", user_data.format_for_cloudformation()]}
    else:
        parsed_user_data = user_data

    config = configuration.CloudFormationConfiguration(domain, PRODUCTION_REGION)
    # Prepare user data for parsing by CloudFormation.
    parsed_user_data = { "Fn::Join" : ["", user_data.format_for_cloudformation()]}

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

    role = lib.role_arn_lookup(session, "lambda_cache_execution")
    config.add_arg(configuration.Arg.String("LambdaCacheExecutionRole", role,
                                            "IAM role for multilambda." + domain))

    index_bucket_name = names.get_cuboid_bucket(domain)
    if not lib.s3_bucket_exists(session, index_bucket_name):
        config.add_s3_bucket("cuboidBucket", index_bucket_name)
    config.add_s3_bucket_policy(
        "cuboidBucketPolicy", index_bucket_name,
        ['s3:GetObject', 's3:PutObject'],
        { 'AWS': role})

    tile_bucket_name = names.get_tile_bucket(domain)
    if not lib.s3_bucket_exists(session, tile_bucket_name):
        config.add_s3_bucket("tileBucket", tile_bucket_name)
    config.add_s3_bucket_policy(
        "tileBucketPolicy", tile_bucket_name,
        ['s3:GetObject', 's3:PutObject'],
        { 'AWS': role})

    config.add_ec2_instance("CacheManager",
                                names.get_cache_manager(domain),
                                lib.ami_lookup(session, "cachemanager.boss"),
                                keypair,
                                subnet="InternalSubnet",
                                public_ip=False,
                                type_=CACHE_MANAGER_TYPE,
                                security_groups=["InternalSecurityGroup"],
                                user_data=parsed_user_data,
                                role="cachemanager")

    lambda_sec_group = lib.sg_lookup(session, vpc_id, 'internal.' + domain)
    filter_by_host_name = ([{
        'Name': 'tag:Name',
        'Values': ['*internal.' + domain]
    }])
    lambda_subnets = lib.multi_subnet_id_lookup(session, filter_by_host_name)

    multi_lambda_name = names.get_multi_lambda(domain).replace('.', '-')
    config.add_lambda("MultiLambda",
                      multi_lambda_name,
                      "LambdaCacheExecutionRole",
                      s3=("boss-lambda-env",
                          "multilambda.{}.zip".format(domain),
                          "local/lib/python3.4/site-packages/lambda/lambda_loader.handler"),
                      timeout=60,
                      memory=1024,
                      security_groups=[lambda_sec_group],
                      subnets=lambda_subnets)

    # Add topic to indicating that the object store has been write locked.
    write_lock_topic = WRITE_LOCK_SNS_PREFIX
    write_lock_topic_logical_name = (
        write_lock_topic + '-' + domain.replace('.', '-'))
    # ToDo: add subscribers.
    write_lock_subscribers = []
    config.add_sns_topic(
        write_lock_topic, write_lock_topic,
        write_lock_topic_logical_name, write_lock_subscribers)

    return config


def generate(folder, domain):
    """Create the configuration and save it to disk"""
    name = lib.domain_to_stackname(names.get_cache_db(domain))
    config = create_config(None, domain)
    config.generate(name, folder)


def create(session, domain):
    """Create the configuration, and launch it"""
    s3flushqname = lib.domain_to_stackname(S3FLUSH_QUEUE_PREFIX + domain)
    deadqname = lib.domain_to_stackname(DEADLETTER_QUEUE_PREFIX + domain)

    # Configure Vault and create the user data config that the endpoint will
    # use for connecting to Vault and the DB instance
    user_data = configuration.UserData()
    user_data["system"]["fqdn"] = names.get_cache_manager(domain)
    user_data["system"]["type"] = "cachemanager"
    user_data["aws"]["cache"] = "cache." + domain
    user_data["aws"]["cache-state"] = "cache-state." + domain
    user_data["aws"]["cache-db"] = "0"
    user_data["aws"]["cache-state-db"] = "0"

    # Use CloudFormation's Ref function so that queues' URLs are placed into
    # the Boss config file.
    # user_data["aws"]["s3-flush-queue"] = '{{"Ref": "{}" }}'.format(s3flushqname)
    # user_data["aws"]["s3-flush-deadletter-queue"] = '{{"Ref": "{}" }}'.format(deadqname)

    # Until merged with production.py, look up queue urls instead of using
    # the Ref intrinsic function.
    user_data["aws"]["s3-flush-queue"] = lib.sqs_lookup_url(session, s3flushqname)
    user_data["aws"]["s3-flush-deadletter-queue"] = lib.sqs_lookup_url(session, deadqname)

    user_data["aws"]["cuboid_bucket"] = names.get_cuboid_bucket(domain)
    user_data["aws"]["s3-index-table"] = names.get_s3_index(domain)

    # SNS and Lambda names can't have periods.
    multilambda = names.get_multi_lambda(domain).replace('.', '-')
    user_data["aws"]["sns-write-locked"] = '{{"Ref": "{}"}}'.format(WRITE_LOCK_SNS_PREFIX)

    user_data["lambda"]["flush_function"] = multilambda
    user_data["lambda"]["page_in_function"] = multilambda

    keypair = lib.keypair_lookup(session)

    try:
        name = lib.domain_to_stackname(names.get_cache_db(domain))
        pre_init(session, domain)

        config = create_config(session, domain, keypair, user_data)

        success = config.create(session, name)
        print("finished config.create")
        if not success:
            raise Exception("Create Failed")
        else:
            post_init(session, domain)
    except:
        print("Error detected") # Do we want to revoke if an exception from post_init?
        raise


def pre_init(session, domain):
    """Send spdb, bossutils, lambda, and lambda_utils to the lambda build
    server, build the lambda environment, and upload to S3.
    """
    load_lambdas_on_s3(domain)

def post_init(session, domain):
    print("post_init")

    # Tell Scalyr to get CloudWatch metrics for these instances.
    instances = [names.get_cache_manager(domain)]
    scalyr.add_instances_to_scalyr(
        session, PRODUCTION_REGION, instances)



def delete(session, domain):
    # NOTE: CloudWatch logs for the DNS Lambda are not deleted
    lib.delete_stack(session, domain, "cachedb")
    lib.route53_delete_records(session, domain, names.get_cache_manager(domain))

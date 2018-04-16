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

DEPENDENCIES = ['core', 'redis', 'api']

from lib.cloudformation import CloudFormationConfiguration, Arg, Ref
from lib.userdata import UserData
from lib.names import AWSNames
from lib.external import ExternalCalls
from lib import aws
from lib import scalyr
from lib import constants as const

from update_lambda_fcn import load_lambdas_on_s3
import boto3


def create_config(bosslet_config, user_data=None):
    # Prepare user data for parsing by CloudFormation.
    if user_data is not None:
        parsed_user_data = { "Fn::Join" : ["", user_data.format_for_cloudformation()]}
    else:
        parsed_user_data = user_data

    keypair = bosslet_config.SSH_KEY
    session = bosslet_config.session
    names = AWSNames(bosslet_config)
    config = CloudFormationConfiguration("cachedb", bosslet_config)

    vpc_id = config.find_vpc()

    #####
    # TODO: When CF config files are refactored for multi-account support
    #       the creation of _all_ subnets should be moved into core.
    #       AWS doesn't charge for the VPC or subnets, so it doesn't
    #       increase cost and cleans up subnet creation

    # Create several subnets for all the lambdas to use.
    internal_route_table_id = aws.rt_lookup(session, vpc_id, names.rt.internal)

    lambda_subnets = config.add_all_lambda_subnets()
    for lambda_subnet in lambda_subnets:
        key = lambda_subnet['Ref']
        config.add_route_table_association(key + "RTA",
                                           internal_route_table_id,
                                           lambda_subnet)

    # Lookup the External Subnet, Internal Security Group IDs that are
    # needed by other resources
    internal_subnet_id = aws.subnet_id_lookup(session, names.subnet.internal)
    config.add_arg(Arg.Subnet("InternalSubnet",
                              internal_subnet_id,
                              "ID of Internal Subnet to create resources in"))

    internal_sg_id = aws.sg_lookup(session, vpc_id, names.sg.internal)
    config.add_arg(Arg.SecurityGroup("InternalSecurityGroup",
                                     internal_sg_id,
                                     "ID of internal Security Group"))

    role = aws.role_arn_lookup(session, "lambda_cache_execution")
    config.add_arg(Arg.String("LambdaCacheExecutionRole", role,
                              "IAM role for " + names.lambda_.multi_lambda))

    index_bucket_name = names.s3.cuboid_bucket
    if not aws.s3_bucket_exists(session, index_bucket_name):
        config.add_s3_bucket("cuboidBucket", index_bucket_name)
    config.add_s3_bucket_policy(
        "cuboidBucketPolicy", index_bucket_name,
        ['s3:GetObject', 's3:PutObject'],
        { 'AWS': role})

    delete_bucket_name = names.s3.delete_bucket
    if not aws.s3_bucket_exists(session, delete_bucket_name):
        config.add_s3_bucket("deleteBucket", delete_bucket_name)
    config.add_s3_bucket_policy(
        "deleteBucketPolicy", delete_bucket_name,
        ['s3:GetObject', 's3:PutObject'],
        { 'AWS': role})

    creating_tile_bucket = False
    tile_bucket_name = names.s3.tile_bucket
    if not aws.s3_bucket_exists(session, tile_bucket_name):
        creating_tile_bucket = True
        config.add_s3_bucket("tileBucket", tile_bucket_name)

    config.add_s3_bucket_policy(
        "tileBucketPolicy", tile_bucket_name,
        ['s3:GetObject', 's3:PutObject'],
        { 'AWS': role})

    ingest_bucket_name = names.s3.ingest_bucket
    if not aws.s3_bucket_exists(session, ingest_bucket_name):
        config.add_s3_bucket("ingestBucket", ingest_bucket_name)
    config.add_s3_bucket_policy(
        "ingestBucketPolicy", ingest_bucket_name,
        ['s3:GetObject', 's3:PutObject'],
        { 'AWS': role})

    config.add_ec2_instance("CacheManager",
                            names.dns.cache_manager,
                            aws.ami_lookup(bosslet_config, names.ami.cache_manager),
                            keypair,
                            subnet=Ref("InternalSubnet"),
                            public_ip=False,
                            type_=const.CACHE_MANAGER_TYPE,
                            security_groups=[Ref("InternalSecurityGroup")],
                            user_data=parsed_user_data,
                            role="cachemanager")

    config.add_lambda("MultiLambda",
                      names.lambda_.multi_lambda,
                      Ref("LambdaCacheExecutionRole"),
                      s3=(bosslet_config.LAMBDA_BUCKET,
                          "multilambda.{}.zip".format(bosslet_config.INTERNAL_DOMAIN),
                          "lambda_loader.handler"),
                      timeout=120,
                      memory=1024,
                      security_groups=[Ref('InternalSecurityGroup')],
                      subnets=lambda_subnets,
                      runtime='python3.6')

    if creating_tile_bucket:
        config.add_lambda_permission('tileBucketInvokeMultiLambda',
                                     names.lambda_.multi_lambda,
                                     principal='s3.amazonaws.com',
                                     source={ 'Fn::Join': [':', ['arn', 'aws', 's3', '', '', tile_bucket_name]]}, #DP TODO: move into constants
                                     depends_on=['tileBucket', 'MultiLambda'])
    else:
        config.add_lambda_permission('tileBucketInvokeMultiLambda',
                                     names.lambda_.multi_lambda,
                                     principal='s3.amazonaws.com',
                                     source={ 'Fn::Join': [':', ['arn', 'aws', 's3', '', '', tile_bucket_name]]},
                                     depends_on='MultiLambda')

    # Add topic to indicating that the object store has been write locked.
    # Now using "production mailing list" instead of separate write lock topic.
    #config.add_sns_topic('WriteLock',
    #                     names.write_lock_topic,
    #                     names.write_lock,
    #                     []) # TODO: add subscribers

    return config


def generate(bosslet_config):
    """Create the configuration and save it to disk"""
    config = create_config(bosslet_config)
    config.generate()


def create(bosslet_config):
    """Create the configuration, and launch it"""
    names = AWSNames(bosslet_config)
    session = bosslet_config.session

    user_data = UserData()
    user_data["system"]["fqdn"] = names.dns.cache_manager
    user_data["system"]["type"] = "cachemanager"
    user_data["aws"]["cache"] = names.redis.cache
    user_data["aws"]["cache-state"] = names.redis.cache_state
    user_data["aws"]["cache-db"] = "0"
    user_data["aws"]["cache-state-db"] = "0"

    user_data["aws"]["s3-flush-queue"] = aws.sqs_lookup_url(session, names.sqs.s3flush)
    user_data["aws"]["s3-flush-deadletter-queue"] = aws.sqs_lookup_url(session, names.sqs.deadletter)

    user_data["aws"]["cuboid_bucket"] = names.s3.cuboid_bucket
    user_data["aws"]["ingest_bucket"] = names.s3.ingest_bucket
    user_data["aws"]["s3-index-table"] = names.ddb.s3_index
    user_data["aws"]["id-index-table"] = names.ddb.id_index
    user_data["aws"]["id-count-table"] = names.ddb.id_count_index

    #user_data["aws"]["sns-write-locked"] = str(Ref('WriteLock'))

    mailing_list_arn = aws.sns_topic_lookup(session, const.PRODUCTION_MAILING_LIST)
    if mailing_list_arn is None:
        msg = "MailingList {} needs to be created before running config".format(const.PRODUCTION_MAILING_LIST)
        raise Exception(msg)
    user_data["aws"]["sns-write-locked"] = mailing_list_arn

    user_data["lambda"]["flush_function"] = names.lambda_.multi_lambda
    user_data["lambda"]["page_in_function"] = names.lambda_.multi_lambda

    try:
        pre_init(bosslet_config)

        config = create_config(bosslet_config, user_data)

        success = config.create()
        if success:
            success = post_init(bosslet_config)

        return success
    except:
        # DP NOTE: This will catch errors from pre_init, create, and post_init
        print("Error detected")
        raise


def pre_init(bosslet_config):
    """Send spdb, bossutils, lambda, and lambda_utils to the lambda build
    server, build the lambda environment, and upload to S3.
    """
    load_lambdas_on_s3(bosslet_config)


def post_init(bosslet_config):
    print("post_init")

    print('adding tile bucket trigger of multi-lambda')
    add_tile_bucket_trigger(bosslet_config)

    # Tell Scalyr to get CloudWatch metrics for these instances.
    names = AWSNames(bosslet_config)
    instances = [names.dns.cache_manager]
    scalyr.add_instances_to_scalyr(
        session, bosslet_config.REGION, instances)

    return True

def add_tile_bucket_trigger(bosslet_config):
    """Trigger MultiLambda when file uploaded to tile bucket.

    This is done in post-init() because the tile bucket isn't always
    created during CloudFormation (it may already exist).

    This function's effects should be idempotent because the same id is
    used everytime the notification event is added to the tile bucket.

    Args:
        session (Boto3.Session)
        domain (string): VPC domain name.
    """
    session = bosslet_config.session
    names = AWSNames(bosslet_config)
    lambda_name = names.lambda_.multi_lambda
    bucket_name = names.s3.tile_bucket

    lam = session.client('lambda')
    resp = lam.get_function_configuration(FunctionName=lambda_name)
    lambda_arn = resp['FunctionArn']

    s3 = session.resource('s3')
    bucket = s3.Bucket(bucket_name)

    notification = bucket.Notification()
    notification.put(NotificationConfiguration={
        'LambdaFunctionConfigurations': [
            {
                'Id': 'tileBucketInvokeMultiLambda',
                'LambdaFunctionArn': lambda_arn,
                'Events': ['s3:ObjectCreated:*']
            }
        ]
    })


def delete(bosslet_config):
    # NOTE: CloudWatch logs for the DNS Lambda are not deleted
    session = bosslet_config.session
    domain = bosslet_config.INTERNAL_DOMAIN
    names = AWSNames(domain)

    aws.route53_delete_records(session, domain, names.dns.cache_manager)

    config = CloudFormationConfiguration("cachedb", bosslet_config)
    success = config.delete()
    return success

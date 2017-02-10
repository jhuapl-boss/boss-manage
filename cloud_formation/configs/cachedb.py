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

from lib.cloudformation import CloudFormationConfiguration, Arg, Ref
from lib.userdata import UserData
from lib.names import AWSNames
from lib.external import ExternalCalls
from lib import aws
from lib import scalyr
from lib import constants as const

from update_lambda_fcn import load_lambdas_on_s3
import boto3

def create_config(session, domain, keypair=None, user_data=None):
    """
    Create the CloudFormationConfiguration object.
    Args:
        session: amazon session object
        domain: domain of the stack being created
        keypair: keypair used to by instances being created
        user_data (UserData): information used by the endpoint instance and vault.  Data will be run through the CloudFormation Fn::Join template intrinsic function so other template intrinsic functions used in the user_data will be parsed and executed.

    Returns: the config for the Cloud Formation stack

    """

    # Prepare user data for parsing by CloudFormation.
    if user_data is not None:
        parsed_user_data = { "Fn::Join" : ["", user_data.format_for_cloudformation()]}
    else:
        parsed_user_data = user_data

    names = AWSNames(domain)
    config = CloudFormationConfiguration("cachedb", domain, const.REGION)

    vpc_id = config.find_vpc(session)
    internal_subnets, _ = config.find_all_availability_zones(session)

    # Lookup the External Subnet, Internal Security Group IDs that are
    # needed by other resources
    internal_subnet_id = aws.subnet_id_lookup(session, names.subnet("internal"))
    config.add_arg(Arg.Subnet("InternalSubnet",
                              internal_subnet_id,
                              "ID of Internal Subnet to create resources in"))

    internal_sg_id = aws.sg_lookup(session, vpc_id, names.internal)
    config.add_arg(Arg.SecurityGroup("InternalSecurityGroup",
                                     internal_sg_id,
                                     "ID of internal Security Group"))

    role = aws.role_arn_lookup(session, "lambda_cache_execution")
    config.add_arg(Arg.String("LambdaCacheExecutionRole", role,
                              "IAM role for multilambda." + domain))

    index_bucket_name = names.cuboid_bucket
    if not aws.s3_bucket_exists(session, index_bucket_name):
        config.add_s3_bucket("cuboidBucket", index_bucket_name)
    config.add_s3_bucket_policy(
        "cuboidBucketPolicy", index_bucket_name,
        ['s3:GetObject', 's3:PutObject'],
        { 'AWS': role})

    creating_tile_bucket = False
    tile_bucket_name = names.tile_bucket
    if not aws.s3_bucket_exists(session, tile_bucket_name):
        creating_tile_bucket = True
        config.add_s3_bucket("tileBucket", tile_bucket_name)

    config.add_s3_bucket_policy(
        "tileBucketPolicy", tile_bucket_name,
        ['s3:GetObject', 's3:PutObject'],
        { 'AWS': role})

    ingest_bucket_name = names.ingest_bucket
    if not aws.s3_bucket_exists(session, ingest_bucket_name):
        config.add_s3_bucket("ingestBucket", ingest_bucket_name)
    config.add_s3_bucket_policy(
        "ingestBucketPolicy", ingest_bucket_name,
        ['s3:GetObject', 's3:PutObject'],
        { 'AWS': role})

    config.add_ec2_instance("CacheManager",
                                names.cache_manager,
                                aws.ami_lookup(session, "cachemanager.boss"),
                                keypair,
                                subnet=Ref("InternalSubnet"),
                                public_ip=False,
                                type_=const.CACHE_MANAGER_TYPE,
                                security_groups=[Ref("InternalSecurityGroup")],
                                user_data=parsed_user_data,
                                role="cachemanager")

    lambda_bucket = aws.get_lambda_s3_bucket(session)
    config.add_lambda("MultiLambda",
                      names.multi_lambda,
                      Ref("LambdaCacheExecutionRole"),
                      s3=(aws.get_lambda_s3_bucket(session),
                          "multilambda.{}.zip".format(domain),
                          "local/lambda_loader.handler"),
                      timeout=120,
                      memory=1024,
                      security_groups=[Ref('InternalSecurityGroup')],
                      subnets=internal_subnets)

    if creating_tile_bucket:
        config.add_lambda_permission(
            'tileBucketInvokeMultiLambda', names.multi_lambda,
            principal='s3.amazonaws.com', source={
                'Fn::Join': [':', ['arn', 'aws', 's3', '', '', tile_bucket_name]]}, #DP TODO: move into constants
            depends_on=['tileBucket', 'MultiLambda']
        )
    else:
        config.add_lambda_permission(
            'tileBucketInvokeMultiLambda', names.multi_lambda,
            principal='s3.amazonaws.com', source={
                'Fn::Join': [':', ['arn', 'aws', 's3', '', '', tile_bucket_name]]},
            depends_on='MultiLambda'
        )

    # Add topic to indicating that the object store has been write locked.
    config.add_sns_topic('WriteLock',
                         names.write_lock_topic,
                         names.write_lock,
                         []) # TODO: add subscribers

    return config


def generate(session, domain):
    """Create the configuration and save it to disk"""
    config = create_config(session, domain)
    config.generate()


def create(session, domain):
    """Create the configuration, and launch it"""
    names = AWSNames(domain)

    user_data = UserData()
    user_data["system"]["fqdn"] = names.cache_manager
    user_data["system"]["type"] = "cachemanager"
    user_data["aws"]["cache"] = names.cache
    user_data["aws"]["cache-state"] = names.cache_state
    user_data["aws"]["cache-db"] = "0"
    user_data["aws"]["cache-state-db"] = "0"

    user_data["aws"]["s3-flush-queue"] = aws.sqs_lookup_url(session, names.s3flush_queue)
    user_data["aws"]["s3-flush-deadletter-queue"] = aws.sqs_lookup_url(session, names.deadletter_queue)

    user_data["aws"]["cuboid_bucket"] = names.cuboid_bucket
    user_data["aws"]["ingest_bucket"] = names.ingest_bucket
    user_data["aws"]["s3-index-table"] = names.s3_index
    user_data["aws"]["id-index-table"] = names.id_index
    user_data["aws"]["id-count-table"] = names.id_count_index

    # SNS and Lambda names can't have periods.
    user_data["aws"]["sns-write-locked"] = str(Ref('WriteLock'))

    user_data["lambda"]["flush_function"] = names.multi_lambda
    user_data["lambda"]["page_in_function"] = names.multi_lambda

    keypair = aws.keypair_lookup(session)

    try:
        pre_init(session, domain)

        config = create_config(session, domain, keypair, user_data)

        success = config.create(session)
        if not success:
            raise Exception("Create Failed")
        else:
            post_init(session, domain)
    except:
        # DP NOTE: This will catch errors from pre_init, create, and post_init
        print("Error detected")
        raise


def pre_init(session, domain):
    """Send spdb, bossutils, lambda, and lambda_utils to the lambda build
    server, build the lambda environment, and upload to S3.
    """

    bucket = aws.get_lambda_s3_bucket(session)
    load_lambdas_on_s3(session, domain, bucket)


def post_init(session, domain):
    print("post_init")

    print('adding tile bucket trigger of multi-lambda')
    add_tile_bucket_trigger(session, domain)

    # Tell Scalyr to get CloudWatch metrics for these instances.
    names = AWSNames(domain)
    instances = [names.cache_manager]
    scalyr.add_instances_to_scalyr(
        session, const.REGION, instances)

def add_tile_bucket_trigger(session, domain):
    """Trigger MultiLambda when file uploaded to tile bucket.

    This is done in post-init() because the tile bucket isn't always
    created during CloudFormation (it may already exist).

    This function's effects should be idempotent because the same id is
    used everytime the notification event is added to the tile bucket.

    Args:
        session (Boto3.Session)
        domain (string): VPC domain name.
    """
    names = AWSNames(domain)
    lambda_name = names.multi_lambda
    bucket_name = names.tile_bucket

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


def delete(session, domain):
    # NOTE: CloudWatch logs for the DNS Lambda are not deleted
    names = AWSNames(domain)
    aws.route53_delete_records(session, domain, names.cache_manager)
    CloudFormationConfiguration("cachedb", domain).delete(session)

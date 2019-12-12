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
"""

DEPENDENCIES = ['core', 'redis', 'api']

from lib.bucket_object_tags import TAG_DELETE_KEY, TAG_DELETE_VALUE
from lib.cloudformation import CloudFormationConfiguration, Arg, Ref, Arn
from lib.userdata import UserData
from lib.exceptions import MissingResourceError
from lib import aws
from lib import constants as const
from lib import utils
from lib import console
from lib.lambdas import load_lambdas_on_s3, update_lambda_code

import botocore

# Number of days until objects expire in the tile bucket.
EXPIRE_IN_DAYS = 21

# Number of days to wait before deleting an object marked for deletion.
MARKED_FOR_DELETION_DAYS = 3

# Ids used for bucket lambda triggers.
INGEST_BUCKET_TRIGGER = 'ingestBucketInvokeCuboidImportLambda'

CUBOID_IMPORT_ROLE = 'CuboidImportLambdaRole'


def get_cf_bucket_life_cycle_rules():
    """
    Generate the CloudFormation expiration policy for the tile bucket.  This is
    a fallback in case tiles aren't cleaned up properly, post-ingest.  Messages 
    n the ingest queue only last 14 days, so removing the S3 objects 7 days
    after should be plenty of time.

    This policy is also now used for the ingest bucket to ensure removal of
    cuboids uploaded during volumetric ingest.

    This policy now contains a new rule to expire an object 1 day after it's
    marked with a delete tag.  Objects are now marked for deletion (instead
    of immediate deletion) by lambdas triggered by bucket uploads to maintain
    idempotentness.
    """
    return {
        'Rules': [
            {
                'ExpirationInDays': EXPIRE_IN_DAYS,
                'Status': 'Enabled',
            },
            {
                # Marked for deletion rule.
                'ExpirationInDays': MARKED_FOR_DELETION_DAYS,
                'Status': 'Enabled',
                'TagFilters': [{
                    'Key': TAG_DELETE_KEY,
                    'Value': TAG_DELETE_VALUE
                }]
            }
        ]
    }

def get_boto_bucket_life_cycle_rules():
    """
    Generate the boto expiration policy for the tile bucket.  This is
    a fallback in case tiles aren't cleaned up properly, post-ingest.  Messages 
    n the ingest queue only last 14 days, so removing the S3 objects 7 days
    after should be plenty of time.

    This policy is also now used for the ingest bucket to ensure removal of
    cuboids uploaded during volumetric ingest.

    This policy now contains a new rule to expire an object 1 day after it's
    marked with a delete tag.  Objects are now marked for deletion (instead
    of immediate deletion) by lambdas triggered by bucket uploads to maintain
    idempotentness.
    """
    return {
        'Rules': [
            {
                'Expiration': { 'Days': EXPIRE_IN_DAYS},
                'Status': 'Enabled',
                'Filter': {}
            },
            {
                # Marked for deletion rule.
                'Expiration': { 'Days': MARKED_FOR_DELETION_DAYS },
                'Status': 'Enabled',
                'Filter': {
                    'Tag': {
                        'Key': TAG_DELETE_KEY,
                        'Value': TAG_DELETE_VALUE }
                }
            }
        ]
    }


def get_s3_index_arn(bosslet_config):
    """
    Get arn of the DynamoDB s3 index.

    Args:
        bosslet_config (BossConfiguration): target bosslet

    Returns:
        (str):
    """
    names = bosslet_config.names
    dynamo = bosslet_config.session.client('dynamodb')
    resp = dynamo.describe_table(TableName=names.s3_index.ddb)
    return resp['Table']['TableArn']


def create_config(bosslet_config, user_data=None):
    """
    Create the CloudFormationConfiguration object.
    Args:
        bosslet_config (BossConfiguration): target bosslet
        user_data (UserData): information used by the endpoint instance and vault.  Data will be run through the CloudFormation Fn::Join template intrinsic function so other template intrinsic functions used in the user_data will be parsed and executed.

    Returns: the config for the Cloud Formation stack

    """

    # Prepare user data for parsing by CloudFormation.
    if user_data is not None:
        parsed_user_data = { "Fn::Join" : ["", user_data.format_for_cloudformation()]}
    else:
        parsed_user_data = user_data

    keypair = bosslet_config.SSH_KEY
    session = bosslet_config.session
    names = bosslet_config.names
    config = CloudFormationConfiguration("cachedb", bosslet_config)

    vpc_id = config.find_vpc()

    #####
    # TODO: When CF config files are refactored for multi-account support
    #       the creation of _all_ subnets should be moved into core.
    #       AWS doesn't charge for the VPC or subnets, so it doesn't
    #       increase cost and cleans up subnet creation

    # Create several subnets for all the lambdas to use.
    internal_route_table_id = aws.rt_lookup(session, vpc_id, names.internal.rt)

    lambda_subnets = config.add_all_lambda_subnets()
    for lambda_subnet in lambda_subnets:
        key = lambda_subnet['Ref']
        config.add_route_table_association(key + "RTA",
                                           internal_route_table_id,
                                           lambda_subnet)

    # Create a custom resource to help delete ENIs from lambdas
    # DP NOTE: After deleting a lambda the ENIs may stick around for while, causing the stack delete to fail
    #          See https://stackoverflow.com/a/41310289
    config.add_arg(Arg.String('StackName', config.stack_name))
    config.add_arg(Arg.String('DeleteENILambda', aws.lambda_arn_lookup(session, names.delete_eni.lambda_)))
    config.add_custom_resource('DeleteENI', 'DeleteENI', Ref('DeleteENILambda'), StackName = Ref('StackName'))

    # Lookup the External Subnet, Internal Security Group IDs that are
    # needed by other resources
    internal_subnet_id = aws.subnet_id_lookup(session, names.internal.subnet)
    config.add_arg(Arg.Subnet("InternalSubnet",
                              internal_subnet_id,
                              "ID of Internal Subnet to create resources in"))

    internal_sg_id = aws.sg_lookup(session, vpc_id, names.internal.sg)
    config.add_arg(Arg.SecurityGroup("InternalSecurityGroup",
                                     internal_sg_id,
                                     "ID of internal Security Group"))

    role = aws.role_arn_lookup(session, "lambda_cache_execution")
    config.add_arg(Arg.String("LambdaCacheExecutionRole", role,
                              "IAM role for " + names.multi_lambda.lambda_))

    cuboid_import_role = aws.role_arn_lookup(session, CUBOID_IMPORT_ROLE)
    config.add_arg(Arg.String(CUBOID_IMPORT_ROLE, cuboid_import_role,
                              "IAM role for cuboidImport"))

    config.add_capabilities(['CAPABILITY_IAM'])
 
    cuboid_bucket_name = names.cuboid_bucket.s3
    if not aws.s3_bucket_exists(session, cuboid_bucket_name):
        config.add_s3_bucket("cuboidBucket", cuboid_bucket_name)

    config.add_s3_bucket_policy(
        "cuboidBucketPolicy", cuboid_bucket_name,
        ['s3:GetObject', 's3:PutObject'],
        { 'AWS': role})
    config.append_s3_bucket_policy(
        "cuboidBucketPolicy", cuboid_bucket_name,
        ['s3:PutObject'], { 'AWS': cuboid_import_role})

    delete_bucket_name = names.delete_bucket.s3
    if not aws.s3_bucket_exists(session, delete_bucket_name):
        config.add_s3_bucket("deleteBucket", delete_bucket_name)
    config.add_s3_bucket_policy(
        "deleteBucketPolicy", delete_bucket_name,
        ['s3:GetObject', 's3:PutObject'],
        { 'AWS': role})

    tile_bucket_name = names.tile_bucket.s3
    if not aws.s3_bucket_exists(session, tile_bucket_name):
        life_cycle_cfg = get_cf_bucket_life_cycle_rules()
        config.add_s3_bucket(
            "tileBucket", tile_bucket_name, life_cycle_config=life_cycle_cfg)

    config.add_s3_bucket_policy(
        "tileBucketPolicy", tile_bucket_name,
        ['s3:GetObject', 's3:PutObject'],
        { 'AWS': role})

    # The ingest bucket is a staging area for cuboids uploaded during volumetric ingest.
    creating_ingest_bucket = False
    ingest_bucket_name = names.ingest_bucket.s3
    if not aws.s3_bucket_exists(session, ingest_bucket_name):
        creating_ingest_bucket = True
        ing_bucket_life_cycle_cfg = get_cf_bucket_life_cycle_rules()
        config.add_s3_bucket("ingestBucket", ingest_bucket_name,
            life_cycle_config=ing_bucket_life_cycle_cfg)

    config.add_s3_bucket_policy(
        "ingestBucketPolicy", ingest_bucket_name,
        ['s3:GetObject', 's3:PutObject', 's3:PutObjectTagging'],
        { 'AWS': cuboid_import_role})

    config.add_ec2_instance("CacheManager",
                            names.cachemanager.dns,
                            aws.ami_lookup(bosslet_config, names.cachemanager.ami),
                            keypair,
                            subnet=Ref("InternalSubnet"),
                            public_ip=False,
                            type_=const.CACHE_MANAGER_TYPE,
                            security_groups=[Ref("InternalSecurityGroup")],
                            user_data=parsed_user_data,
                            role="cachemanager")

    config.add_sqs_queue(
        names.ingest_cleanup_dlq.sqs, names.ingest_cleanup_dlq.sqs, 30, 20160)
    config.add_sqs_queue(
        names.cuboid_import_dlq.sqs, names.cuboid_import_dlq.sqs, 30, 20160)

    config.add_sqs_policy('cuboidImportDlqPolicy', 'cuboidImportDlqPolicy',
        [Ref(names.cuboid_import_dlq.sqs)], cuboid_import_role)

    config.add_lambda("MultiLambda",
                      names.multi_lambda.lambda_,
                      Ref("LambdaCacheExecutionRole"),
                      s3=(bosslet_config.LAMBDA_BUCKET,
                          names.multi_lambda.zip,
                          "lambda_loader.handler"),
                      timeout=120,
                      memory=1536,
                      security_groups=[Ref('InternalSecurityGroup')],
                      subnets=lambda_subnets,
                      runtime='python3.6')
    config.add_lambda("TileUploadedLambda",
                      names.tile_uploaded.lambda_,
                      Ref("LambdaCacheExecutionRole"),
                      s3=(bosslet_config.LAMBDA_BUCKET,
                          names.multi_lambda.zip,
                          "tile_uploaded_lambda.handler"),
                      timeout=5,
                      memory=1024,
                      runtime='python3.6')
    config.add_lambda("TileIngestLambda",
                      names.tile_ingest.lambda_,
                      Ref("LambdaCacheExecutionRole"),
                      s3=(bosslet_config.LAMBDA_BUCKET,
                          names.multi_lambda.zip,
                          "tile_ingest_lambda.handler"),
                      timeout=30,
                      memory=1536,
                      runtime='python3.6')
    config.add_lambda("DeleteTileObjsLambda",
                      names.delete_tile_objs.lambda_,
                      Ref("LambdaCacheExecutionRole"),
                      s3=(bosslet_config.LAMBDA_BUCKET,
                          names.multi_lambda.zip,
                          "delete_tile_objs_lambda.handler"),
                      timeout=90,
                      memory=128,
                      runtime='python3.6',
                      dlq=Arn(names.ingest_cleanup_dlq.sqs))
    config.add_lambda("DeleteTileEntryLambda",
                      names.delete_tile_index_entry.lambda_,
                      Ref("LambdaCacheExecutionRole"),
                      s3=(bosslet_config.LAMBDA_BUCKET,
                          names.multi_lambda.zip,
                          "delete_tile_index_entry_lambda.handler"),
                      timeout=90,
                      memory=128,
                      runtime='python3.6',
                      dlq=Arn(names.ingest_cleanup_dlq.sqs))
    config.add_lambda("CuboidImportLambda",
                      names.cuboid_import_lambda.lambda_,
                      Ref(CUBOID_IMPORT_ROLE),
                      s3=(bosslet_config.LAMBDA_BUCKET,
                          names.multi_lambda.zip,
                          "cuboid_import_lambda.handler"),
                      timeout=90,
                      memory=128,
                      runtime='python3.6',
                      dlq=Arn(names.cuboid_import_dlq.sqs))
    config.add_lambda("VolumetricIngestLambda",
                      names.volumetric_ingest_queue_upload_lambda.lambda_,
                      Ref("LambdaCacheExecutionRole"),
                      s3=(bosslet_config.LAMBDA_BUCKET,
                          names.multi_lambda.zip,
                          "ingest_queue_upload_volumetric_lambda.handler"),
                      timeout=120,
                      memory=1024,
                      runtime='python3.6')

    if creating_ingest_bucket:
        config.add_lambda_permission(
            'ingestBucketInvokeCuboidImportLambda', names.cuboid_import_lambda.lambda_,
            principal='s3.amazonaws.com', source={
                'Fn::Join': [':', ['arn', 'aws', 's3', '', '', ingest_bucket_name]]}, #DP TODO: move into constants
            depends_on=['ingestBucket', 'CuboidImportLambda']
        )
    else:
        # NOTE: this permission doesn't seem to apply properly when doing a
        # CloudFormation update.  During testing, I had to manually apply this
        # permission before the bucket trigger could be applied in post_init().
        # Doing a CloudFormation delete followed by a create did not have a
        # problem.
        config.add_lambda_permission(
            'ingestBucketInvokeCuboidImportLambda', names.cuboid_import_lambda.lambda_,
            principal='s3.amazonaws.com', source={
                'Fn::Join': [':', ['arn', 'aws', 's3', '', '', ingest_bucket_name]]},
            depends_on='CuboidImportLambda'
        )

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


def build_user_data(bosslet_config):
    names = bosslet_config.names
    session = bosslet_config.session

    user_data = UserData()
    user_data["system"]["fqdn"] = names.cachemanager.dns
    user_data["system"]["type"] = "cachemanager"
    user_data["aws"]["cache"] = names.cache.redis
    user_data["aws"]["cache-state"] = names.cache_state.redis
    user_data["aws"]["cache-db"] = "0"
    user_data["aws"]["cache-state-db"] = "0"

    user_data["aws"]["s3-flush-queue"] = aws.sqs_lookup_url(session, names.s3flush.sqs)
    user_data["aws"]["s3-flush-deadletter-queue"] = aws.sqs_lookup_url(session, names.deadletter.sqs)

    user_data["aws"]["cuboid_bucket"] = names.cuboid_bucket.s3
    user_data["aws"]["ingest_bucket"] = names.ingest_bucket.s3
    user_data["aws"]["s3-index-table"] = names.s3_index.ddb
    user_data["aws"]["id-index-table"] = names.id_index.ddb
    user_data["aws"]["id-count-table"] = names.id_count_index.ddb

    #user_data["aws"]["sns-write-locked"] = str(Ref('WriteLock'))

    mailing_list_arn = aws.sns_topic_lookup(session, bosslet_config.ALERT_TOPIC)
    if mailing_list_arn is None:
        raise MissingResourceError('SNS topic', bosslet_config.ALERT_TOPIC)
    user_data["aws"]["sns-write-locked"] = mailing_list_arn

    user_data["lambda"]["flush_function"] = names.multi_lambda.lambda_
    user_data["lambda"]["page_in_function"] = names.multi_lambda.lambda_

    return user_data


def create(bosslet_config):
    """Create the configuration, and launch it"""

    user_data = build_user_data(bosslet_config)

    pre_init(bosslet_config)

    config = create_config(bosslet_config, user_data)
    config.create()

    post_init(bosslet_config)


def pre_init(bosslet_config):
    """Send spdb, bossutils, lambda, and lambda_utils to the lambda build
    server, build the lambda environment, and upload to S3.
    """
    load_lambdas_on_s3(bosslet_config)


def update(bosslet_config):
    user_data = build_user_data(bosslet_config)

    config = create_config(bosslet_config, user_data)
    config.update()

    if console.confirm("Rebuild multilambda", default = True):
        pre_init(bosslet_config)
        update_lambda_code(bosslet_config)

    post_init(bosslet_config)


def post_init(bosslet_config):
    print("post_init")

    print('adding ingest bucket trigger of import-cuboid lambda')
    add_bucket_trigger(bosslet_config.session,
                       bosslet_config.names.cuboid_import_lambda.lambda_,
                       bosslet_config.names.ingest_bucket.s3,
                       INGEST_BUCKET_TRIGGER)

    print('setting tile bucket expiration policy')
    check_bucket_life_cycle_policy(bosslet_config.session,
                                   bosslet_config.names.tile_bucket.s3)

    print('setting ingest bucket expiration policy')
    check_bucket_life_cycle_policy(bosslet_config.session,
                                   bosslet_config.names.ingest_bucket.s3)


def check_bucket_life_cycle_policy(session, bucket_name):
    """
    Ensure the expiration policy is attached to the given bucket.

    Args:
        bucket_name (str): Name of S3 bucket.
    """
    s3 = session.client('s3')

    try:
        resp = s3.get_bucket_lifecycle_configuration(Bucket=bucket_name)

        policy_in_place = False
        if 'Rules' in resp:
            for rule in resp['Rules']:
                if 'Expiration' in rule and 'Days' in rule['Expiration']:
                    if (rule['Expiration']['Days'] == EXPIRE_IN_DAYS and 
                            rule['Status'] == 'Enabled'):
                        policy_in_place = True
        if policy_in_place:
            print('policy already set')
            return
    except botocore.exceptions.ClientError as ex:
        if ex.response['Error']['Code'] != 'NoSuchLifecycleConfiguration':
            raise

    print('setting policy')
    s3.put_bucket_lifecycle_configuration(
        Bucket=bucket_name,
        LifecycleConfiguration=get_boto_bucket_life_cycle_rules())


def add_bucket_trigger(session, lambda_name, bucket_name, trigger_id):
    """Trigger lambda when file uploaded to tile bucket.

    This is done in post-init() because the bucket isn't always
    created during CloudFormation (it may already exist).

    This function's effects should be idempotent because the same id is
    used everytime the notification event is added to the bucket.

    Args:
        session (Boto3.Session)
        lambda_name (str): Name of lambda to trigger.
        bucket_name (str): Bucket that triggers lambda.
        trigger_id (str): Name to use for trigger to preserve idempotentness.
    """
    lam = session.client('lambda')
    resp = lam.get_function_configuration(FunctionName=lambda_name)
    lambda_arn = resp['FunctionArn']

    s3 = session.resource('s3')
    bucket = s3.Bucket(bucket_name)

    notification = bucket.Notification()
    notification.put(NotificationConfiguration={
        'LambdaFunctionConfigurations': [
            {
                'Id': trigger_id,
                'LambdaFunctionArn': lambda_arn,
                'Events': ['s3:ObjectCreated:*']
            }
        ]
    })


def delete(bosslet_config):
    # NOTE: CloudWatch logs for the DNS Lambda are not deleted
    session = bosslet_config.session
    domain = bosslet_config.INTERNAL_DOMAIN
    names = bosslet_config.names

    aws.route53_delete_records(session, domain, names.cachemanager.dns)

    config = CloudFormationConfiguration("cachedb", bosslet_config)
    config.delete()

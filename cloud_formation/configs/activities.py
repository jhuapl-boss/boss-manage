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

import json
from lib.cloudformation import CloudFormationConfiguration, Ref, Arn, get_scenario, Arg
from lib.userdata import UserData
from lib.names import AWSNames
from lib import aws
from lib import constants as const
from lib import stepfunctions as sfn
from update_lambda_fcn import load_lambdas_on_s3, update_lambda_code

keypair = None


def create_config(session, domain):
    """Create the CloudFormationConfiguration object."""
    config = CloudFormationConfiguration('activities', domain, const.REGION)
    names = AWSNames(domain)

    global keypair
    keypair = aws.keypair_lookup(session)

    vpc_id = config.find_vpc(session)
    sgs = aws.sg_lookup_all(session, vpc_id)
    internal_subnets, _ = config.find_all_availability_zones(session)
    internal_subnets_lambda, _ = config.find_all_availability_zones(session, lambda_compatible_only=True)
    topic_arn = aws.sns_topic_lookup(session, "ProductionMicronsMailingList")
    event_data = {
        "lambda-name": "delete_lambda",
        "db": names.endpoint_db,
        "meta-db": names.meta,
        "s3-index-table": names.s3_index,
        "id-index-table": names.id_index,
        "id-count-table": names.id_count_index,
        "cuboid_bucket": names.cuboid_bucket,
        "delete_bucket": names.delete_bucket,
        "topic-arn": topic_arn,
        "query-deletes-sfn-name": names.query_deletes,
        "delete-sfn-name": names.delete_cuboid,
        "delete-exp-sfn-name": names.delete_experiment,
        "delete-coord-frame-sfn-name": names.delete_coord_frame,
        "delete-coll-sfn-name": names.delete_collection
    }

    role_arn = aws.role_arn_lookup(session, "events_for_delete_lambda")
    multi_lambda = names.multi_lambda
    lambda_arn = aws.lambda_arn_lookup(session, multi_lambda)
    target_list = [{
        "Arn": lambda_arn,
        "Id": multi_lambda,
        "Input": json.dumps(event_data)
    }]
    schedule_expression = "cron(1 6-11/1 ? * TUE-FRI *)"
    #schedule_expression = "cron(0/2 * * * ? *)"  # testing fire every two minutes

    config.add_event_rule("DeleteEventRule", names.delete_event_rule, role_arn=role_arn,
                          schedule_expression=schedule_expression, target_list=target_list, description=None)
    # Events have to be given permission to run lambda.
    config.add_lambda_permission('DeleteRulePerm', multi_lambda, principal='events.amazonaws.com',
                                 source=Arn('DeleteEventRule'))
    user_data = UserData()
    user_data["system"]["fqdn"] = names.activities
    user_data["system"]["type"] = "activities"
    user_data["aws"]["db"] = names.endpoint_db
    user_data["aws"]["cache"] = names.cache
    user_data["aws"]["cache-state"] = names.cache_state
    user_data["aws"]["cache-db"] = "0"
    user_data["aws"]["cache-state-db"] = "0"
    user_data["aws"]["meta-db"] = names.meta
    user_data["aws"]["cuboid_bucket"] = names.cuboid_bucket
    user_data["aws"]["tile_bucket"] = names.tile_bucket
    user_data["aws"]["ingest_bucket"] = names.ingest_bucket
    user_data["aws"]["s3-index-table"] = names.s3_index
    user_data["aws"]["tile-index-table"] = names.tile_index
    user_data["aws"]["id-index-table"] = names.id_index
    user_data["aws"]["id-count-table"] = names.id_count_index
    user_data["aws"]["downsample-table"] = names.downsample_status

    config.add_autoscale_group("Activities",
                               names.activities,
                               aws.ami_lookup(session, 'activities.boss'),
                               keypair,
                               subnets=internal_subnets_lambda,
                               type_=const.ACTIVITIES_TYPE,
                               security_groups=[sgs[names.internal]],
                               user_data=str(user_data),
                               role=aws.instance_profile_arn_lookup(session, "activities"),
                               min=1,
                               max=1)

    config.add_lambda("IngestLambda",
                      names.ingest_lambda,
                      aws.role_arn_lookup(session, 'IngestQueueUpload'),
                      const.INGEST_LAMBDA,
                      handler="index.handler",
                      timeout=60 * 5)

    config.add_lambda_permission("IngestLambdaExecute", Ref("IngestLambda"))


    # Downsample / Resolution Hierarchy support
    lambda_role = aws.role_arn_lookup(session, "lambda_resolution_hierarchy")

    config.add_lambda("DownsampleVolumeLambda",
                      names.downsample_volume_lambda,
                      lambda_role,
                      s3=(aws.get_lambda_s3_bucket(session),
                          "multilambda.{}.zip".format(domain),
                          "downsample_volume.handler"),
                      timeout=120,
                      memory=1024,
                      runtime='python3.6',
                      dlq = Ref('DownsampleDLQ'))

    config.add_sns_topic("DownsampleDLQ",
                         names.downsample_dlq,
                         names.downsample_dlq,
                         [('lambda', Arn('DownsampleDLQLambda'))])

    config.add_lambda('DownsampleDLQLambda',
                      names.downsample_dlq,
                      lambda_role,
                      const.DOWNSAMPLE_DLQ_LAMBDA,
                      handler='index.handler',
                      timeout=10)

    config.add_lambda_permission('DownsampleDLQLambdaExecute',
                                 Ref('DownsampleDLQLambda'))

    return config


def generate(session, domain):
    """Create the configuration and save it to disk"""
    config = create_config(session, domain)
    config.generate()


def create(session, domain):
    """Create the configuration, launch it, and initialize Vault"""
    resp = input('Rebuild multilambda: [Y/n]:')
    if len(resp) == 0 or (len(resp) > 0 and resp[0] in ('Y', 'y')):
        pre_init(session, domain)

    config = create_config(session, domain)

    success = config.create(session)
    if success:
        post_init(session, domain)


def pre_init(session, domain):
    """Build multilambda zip file and put in S3."""
    bucket = aws.get_lambda_s3_bucket(session)
    load_lambdas_on_s3(session, domain, bucket)


def update(session, domain):
    resp = input('Rebuild multilambda: [Y/n]:')
    if len(resp) == 0 or (len(resp) > 0 and resp[0] in ('Y', 'y')):
        pre_init(session, domain)
        bucket = aws.get_lambda_s3_bucket(session)
        update_lambda_code(session, domain, bucket)

    config = create_config(session, domain)
    success = config.update(session)

    if not success:
        return False

    resp = input('Replace step functions: [Y/n]:')
    if len(resp) == 0 or (len(resp) > 0 and resp[0] in ('Y', 'y')):
        delete_sfns(session, domain)
        post_init(session, domain)

    return True


def post_init(session, domain):
    names = AWSNames(domain)

    sfn.create(session, names.query_deletes, domain, 'query_for_deletes.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(session, names.delete_cuboid, domain, 'delete_cuboid.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(session, names.delete_experiment, domain, 'delete_experiment.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(session, names.delete_coord_frame, domain, 'delete_coordinate_frame.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(session, names.delete_collection, domain, 'delete_collection.hsd', 'StatesExecutionRole-us-east-1 ')
    #sfn.create(session, names.populate_upload_queue, domain, 'populate_upload_queue.hsd',
    #           'StatesExecutionRole-us-east-1 ')
    sfn.create(session, names.ingest_queue_populate, domain, 'ingest_queue_populate.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(session, names.ingest_queue_upload, domain, 'ingest_queue_upload.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(session, names.resolution_hierarchy, domain, 'resolution_hierarchy.hsd', 'StatesExecutionRole-us-east-1')
    #sfn.create(session, names.downsample_volume, domain, 'downsample_volume.hsd', 'StatesExecutionRole-us-east-1')


def delete(session, domain):
    # DP TODO: delete activities
    CloudFormationConfiguration('activities', domain).delete(session)
    delete_sfns(session, domain)


def delete_sfns(session, domain):
    """Delete step functions."""
    names = AWSNames(domain)
    sfn.delete(session, names.delete_cuboid)
    sfn.delete(session, names.delete_experiment)
    sfn.delete(session, names.delete_coord_frame)
    sfn.delete(session, names.delete_collection)
    sfn.delete(session, names.query_deletes)
    sfn.delete(session, names.ingest_queue_populate)
    sfn.delete(session, names.ingest_queue_upload)
    sfn.delete(session, names.resolution_hierarchy)
    #sfn.delete(session, names.downsample_volume)

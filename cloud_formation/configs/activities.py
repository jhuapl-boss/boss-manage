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
Create the activites configuration that consists of
  * Ingest Lambda
  * Step Function Activities server ASG

The activities configuration creates all of the Step Function related resources.
The Activities server run Step Function Activites using the Heaviside library.

As a post-init action the config manually creates the Step Functions by
compiling the Heaviside files.
"""

DEPENDENCIES = ['core', 'api', 'redis', 'cachedb']

import json
from lib.cloudformation import CloudFormationConfiguration, Ref, Arn, Arg
from lib.userdata import UserData
from lib.names import AWSNames
from lib import aws
from lib import constants as const
from lib import stepfunctions as sfn

def create_config(bosslet_config, lookup=True):
    """Create the CloudFormationConfiguration object."""
    config = CloudFormationConfiguration('activities', bosslet_config)
    names = AWSNames(bosslet_config)
    keypair = bosslet_config.SSH_KEY
    session = bosslet_config.session

    vpc_id = config.find_vpc()
    sgs = aws.sg_lookup_all(session, vpc_id)
    internal_subnets, _ = config.find_all_subnets()
    internal_subnets_asg, _ = config.find_all_subnets(compatibility='asg')
    topic_arn = aws.sns_topic_lookup(session, "ProductionMicronsMailingList")
    event_data = {
        "lambda-name": "delete_lambda",
        "db": names.rds.endpoint_db,
        "meta-db": names.ddb.meta,
        "s3-index-table": names.ddb.s3_index,
        "id-index-table": names.ddb.id_index,
        "id-count-table": names.ddb.id_count_index,
        "cuboid_bucket": names.s3.cuboid_bucket,
        "delete_bucket": names.s3.delete_bucket,
        "topic-arn": topic_arn,
        "query-deletes-sfn-name": names.sfn.query_deletes,
        "delete-sfn-name": names.sfn.delete_cuboid,
        "delete-exp-sfn-name": names.sfn.delete_experiment,
        "delete-coord-frame-sfn-name": names.sfn.delete_coord_frame,
        "delete-coll-sfn-name": names.sfn.delete_collection
    }

    role_arn = aws.role_arn_lookup(session, "events_for_delete_lambda")
    multi_lambda = names.lambda_.multi_lambda
    if lookup:
        lambda_arn = aws.lambda_arn_lookup(session, multi_lambda)
    else:
        lambda_arn = None
    target_list = [{
        "Arn": lambda_arn,
        "Id": multi_lambda,
        "Input": json.dumps(event_data)
    }]
    schedule_expression = "cron(1 6-11/1 ? * TUE-FRI *)"
    #schedule_expression = "cron(0/2 * * * ? *)"  # testing fire every two minutes

    config.add_event_rule("DeleteEventRule",
                          # XXX What type for event rules?
                          names.dns.delete_event_rule,
                          role_arn=role_arn,
                          schedule_expression=schedule_expression,
                          target_list=target_list)

    # Events have to be given permission to run lambda.
    config.add_lambda_permission('DeleteRulePerm',
                                 multi_lambda,
                                 principal='events.amazonaws.com',
                                 source=Arn('DeleteEventRule'))
    user_data = UserData()
    user_data["system"]["fqdn"] = names.dns.activities
    user_data["system"]["type"] = "activities"
    user_data["aws"]["db"] = names.rds.endpoint_db
    user_data["aws"]["cache"] = names.redis.cache
    user_data["aws"]["cache-state"] = names.redis.cache_state
    user_data["aws"]["cache-db"] = "0"
    user_data["aws"]["cache-state-db"] = "0"
    user_data["aws"]["meta-db"] = names.ddb.meta
    user_data["aws"]["cuboid_bucket"] = names.s3.cuboid_bucket
    user_data["aws"]["tile_bucket"] = names.s3.tile_bucket
    user_data["aws"]["ingest_bucket"] = names.s3.ingest_bucket
    user_data["aws"]["s3-index-table"] = names.ddb.s3_index
    user_data["aws"]["tile-index-table"] = names.ddb.tile_index
    user_data["aws"]["id-index-table"] = names.ddb.id_index
    user_data["aws"]["id-count-table"] = names.ddb.id_count_index

    config.add_autoscale_group("Activities",
                               names.dns.activities,
                               aws.ami_lookup(bosslet_config, names.ami.activities),
                               keypair,
                               subnets=internal_subnets_asg,
                               type_=const.ACTIVITIES_TYPE,
                               security_groups=[sgs[names.sg.internal]],
                               user_data=str(user_data),
                               role=aws.instance_profile_arn_lookup(session, "activities"),
                               min=1,
                               max=1)

    config.add_lambda("IngestLambda",
                      names.lambda_.ingest_lambda,
                      aws.role_arn_lookup(session, 'IngestQueueUpload'),
                      const.INGEST_LAMBDA,
                      handler="index.handler",
                      timeout=60 * 5)

    config.add_lambda_permission("IngestLambdaExecute", Ref("IngestLambda"))

    return config


def generate(bosslet_config):
    """Create the configuration and save it to disk"""
    config = create_config(bosslet_config, lookup=False)
    config.generate()


def create(bosslet_config):
    """Create the configuration, launch it, and initialize Vault"""
    config = create_config(bosslet_config)

    success = config.create()
    if success:
        success = post_init(bosslet_config)

    return success

def post_init(bosslet_config):
    session = bosslet_config.session
    names = AWSNames(domain)
    domain = bosslet_config.INTERNAL_DOMAIN

    sfn.create(session, names.sfn.query_deletes, domain, 'query_for_deletes.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(session, names.sfn.delete_cuboid, domain, 'delete_cuboid.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(session, names.sfn.delete_experiment, domain, 'delete_experiment.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(session, names.sfn.delete_coord_frame, domain, 'delete_coordinate_frame.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(session, names.sfn.delete_collection, domain, 'delete_collection.hsd', 'StatesExecutionRole-us-east-1 ')
    #sfn.create(session, names.sfn.populate_upload_queue, domain, 'populate_upload_queue.hsd',
    #           'StatesExecutionRole-us-east-1 ')
    sfn.create(session, names.sfn.ingest_queue_populate, domain, 'ingest_queue_populate.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(session, names.sfn.ingest_queue_upload, domain, 'ingest_queue_upload.hsd', 'StatesExecutionRole-us-east-1 ')
    sfn.create(session, names.sfn.resolution_hierarchy, domain, 'resolution_hierarchy.hsd', 'StatesExecutionRole-us-east-1')
    sfn.create(session, names.sfn.downsample_volume, domain, 'downsample_volume.hsd', 'StatesExecutionRole-us-east-1')

    return True

def delete(bosslet_config):
    session = bosslet_config.session
    names = AWSNames(bosslet_config)

    # DP TODO: delete activities
    success = CloudFormationConfiguration('activities', bosslet_config).delete()

    sfn.delete(session, names.sfn.delete_cuboid)
    sfn.delete(session, names.sfn.delete_experiment)
    sfn.delete(session, names.sfn.delete_coord_frame)
    sfn.delete(session, names.sfn.delete_collection)
    sfn.delete(session, names.sfn.query_deletes)
    sfn.delete(session, names.sfn.ingest_queue_populate)
    sfn.delete(session, names.sfn.ingest_queue_upload)
    sfn.delete(session, names.sfn.resolution_hierarchy)
    sfn.delete(session, names.sfn.downsample_volume)

    return success

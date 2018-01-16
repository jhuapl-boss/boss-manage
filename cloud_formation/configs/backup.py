# Copyright 2018 The Johns Hopkins University Applied Physics Laboratory
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
Create a data pipeline that will periodically backup all RDS tables
and DynaamoDB tables to S3 (protected by SSE-S3 data at rest).
"""

from lib.cloudformation import CloudFormationConfiguration
from lib.datapipeline import DataPipeline, Ref
from lib.names import AWSNames
from lib.external import ExternalCalls

from lib import aws
from lib import utils
from lib import scalyr
from lib import constants as const

def rds_copy(pipeline, instance, username, password, db, tables):
    db = db.capitalize()

    pipeline.add_rds_database(db+"DB", instance, username, password)
    for table in tables:
        name = db  + "-" + table.capitalize()
        pipeline.add_rds_table(name, Ref(db+"DB"), table)
        pipeline.add_rds_copy(name+"Copy", Ref(name), Ref("BackupBucket"), Ref("BackupInstance"))

def ddb_copy(pipeline, **tables):
    for name, table in tables.items():
        pipeline.add_ddb_table(name, table)
        pipeline.add_emr_copy(name+"Copy", Ref(name), Ref("BackupBucket"), Ref("BackupCluster"))

def create_config(session, domain):
    """Create the CloudFormationConfiguration object."""
    config = CloudFormationConfiguration('backup', domain, const.REGION)
    names = AWSNames(domain)

    # TODO: lookup endpoint-db credentials
    endpoint_user = None
    endpoint_pass = None

    # TODO: lookup auth-db credentials
    auth_user = None
    auth_pass = None

    # TODO: query for endpoint-db tables
    endpoint_tables = []

    # TODO: query for auth-db tables
    auth_tables = []

    pipeline_role = None
    pipeline_resource_role = None

    pipeline = DataPipeline(pipeline_role, pipeline_resource_role)
    pipeline.add_ec2_instance("BackupInstance")
    pipeline.add_emr_cluster("BackupCluster")
    pipeline.add_s3_bucket("BackupBucket", "backup." + domain) # TODO: create bucket in config

    rds_copy(pipeline,
             names.endpoint_db,
             endpoint_user,
             endpoint_pass,
             "Endpoint",
             endpoint_tables)

    rds_copy(pipeline,
             names.auth_db,
             auth_user,
             auth_pass,
             "Auth",
             auth_tables)

    ddb_copy(pipeline,
             BossMeta = names.meta,
             S3Index = names.s3_index,
             TileIndex = names.tile_index,
             IdIndex = names.id_index,
             IdCountIndex = names.id_count_index)

    config.add_data_pipeline("BackupPipeline", "backup."+domain, pipeline.objects)

    return config

def generate(session, domain):
    """Create the configuration and save it to disk"""
    config = create_config(session, domain)
    config.generate()

def create(session, domain):
    """Create the configuration, launch it, and initialize Vault"""
    config = create_config(session, domain)

    success = config.create(session)
    if success:
        pass

def delete(session, domain):
    names = AWSNames(domain)

    CloudFormationConfiguration('backup', domain).delete(session)

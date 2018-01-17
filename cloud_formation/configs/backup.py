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

import os

try:
    import MySQLdb as mysql
except ImportError:
    print("Rquire MySQLdb library to create backup template")

    import sys
    sys.exit(1)

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

def rds_tables(call, instance, username, password, db):
    print("Looking up tables in database {}".format(db))
    with call.tunnel(instance, 3306, type_='rds') as local_port:
        conn = mysql.connect(host='127.0.0.1',
                             port=local_port,
                             user=username,
                             passwd=password,
                             db=db)

        cur = conn.cursor()
        cur.execute("SHOW TABLES")
        tables = [r[0] for r in cur.fetchall()]
        cur.close()

        conn.close()

    return tables

def create_config(session, domain):
    """Create the CloudFormationConfiguration object."""
    config = CloudFormationConfiguration('backup', domain, const.REGION)
    names = AWSNames(domain)

    keypair = aws.keypair_lookup(session)
    call = ExternalCalls(session, keypair, domain)

    internal_subnet = aws.subnet_id_lookup(session, names.internal)

    pipeline_role = "DataPipelineDefaultRole"
    pipeline_resource_role = "DataPipelineDefaultResourceRole"

    pipeline = DataPipeline(pipeline_role, pipeline_resource_role, "s3://backup."+domain+"/logs")
    pipeline.add_ec2_instance("BackupInstance", subnet=internal_subnet)
    pipeline.add_emr_cluster("BackupCluster")
    pipeline.add_s3_bucket("BackupBucket", "backup." + domain)

    cmd = "curl -X GET 'http://consul:8500/v1/kv/?recurse' > ${OUTPUT1_STAGING_DIR}/consul_data.json"
    pipeline.add_shell_command("ConsulBackup",
                               cmd,
                               destination = Ref("BackupBucket"),
                               runs_on = Ref("BackupInstance"))

    ddb_copy(pipeline,
             BossMeta = names.meta,
             S3Index = names.s3_index,
             TileIndex = names.tile_index,
             IdIndex = names.id_index,
             IdCountIndex = names.id_count_index)

    print("Querying Endpoint DB credentials")
    with call.vault() as vault:
        db_config = vault.read(const.VAULT_ENDPOINT_DB)

        endpoint_user = db_config['user']
        endpoint_pass = db_config['password']

    rds_copy(pipeline,
             names.endpoint_db,
             endpoint_user,
             endpoint_pass,
             "Endpoint",
             rds_tables(call, names.endpoint_db, endpoint_user, endpoint_pass, 'boss'))

    SCENARIO = os.environ["SCENARIO"]
    AUTH_DB = SCENARIO in ("production", "ha-development",)
    if AUTH_DB:
        auth_user = 'keycloak'
        auth_pass = 'keycloak'

        rds_copy(pipeline,
                 names.auth_db,
                 auth_user,
                 auth_pass,
                 "Auth",
                 rds_tables(call, names.auth_db, auth_user, auth_pass, 'keycloak'))

    config.add_data_pipeline("BackupPipeline", "backup."+domain, pipeline.objects)
    config.add_s3_bucket("BackupBucket", "backup." + domain)
    #config.add_s3_bucket_policy("BackupBucketPolicy",
    #                            "backup." + domain,,
    #                            ['s3:GetObject', 's3:PutObject'],
    #                            { 'AWS': role})

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

    resp = input("Delete all backup data [N/y] ")
    if len(resp) == 0 or resp[0] not in ('y', 'Y'):
        print("Not deleting stack")
        return

    CloudFormationConfiguration('backup', domain).delete(session)
    aws.s3_bucket_delete(session, 'backup.' + domain)

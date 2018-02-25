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

def rds_copy(call, rds_name, db_name, db_user, db_pass, subnet, image, s3_logs, s3_backup):
    tables = rds_tables(call, rds_name, db_user, db_pass, db_name)

    # DP TODO: Update the image to read connection information from Vault
    cmd = "mysqldump --opt --host {} --user {} --password={} {} > ${{OUTPUT1_STAGING_DIR}}/{}.sql"
    cmd = cmd.format(rds_name, db_user, db_pass, db_name, db_name)

    pipeline = DataPipeline(log_uri = s3_logs)
    pipeline.add_ec2_instance("RDSInstance",
                              subnet = subnet,
                              image = image)
    pipeline.add_s3_bucket("RDSBucket", s3_backup + "/RDS/" + db_name)
    pipeline.add_shell_command("RDSBackup",
                               cmd,
                               destination = Ref("RDSBucket"),
                               runs_on = Ref("RDSInstance"))
                               
    """
    pipeline.add_rds_database(component + "DB",
                              rds_name.replace('.', '-'), # The instance name is the DNS name without '.',
                              db_user,
                              db_pass)
    for table in tables:
        name = component + "-" + table.capitalize()
        pipeline.add_s3_bucket(name + "Bucket", s3_backup + "/RDS/" + db_name + "/" + table)

        pipeline.add_rds_table(name, Ref(component + "DB"), table)
        pipeline.add_rds_copy(name+"Copy", Ref(name), Ref(name+"Bucket"), Ref(component + "Instance"))
    """

    return pipeline

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
    backup_image = aws.ami_lookup(session, 'backup.boss-test')[0]

    s3_backup = "s3://backup." + domain + "/#{format(@scheduledStartTime, 'YYYY-ww')}"
    s3_logs = "s3://backup." + domain + "/logs"

    config.add_s3_bucket("BackupBucket", "backup." + domain)
    #config.add_s3_bucket_policy("BackupBucketPolicy",
    #                            "backup." + domain,,
    #                            ['s3:GetObject', 's3:PutObject'],
    #                            { 'AWS': role})


    # Consul Backup
    cmd = "curl -X GET 'http://consul.{}:8500/v1/kv/?recurse' > ${{OUTPUT1_STAGING_DIR}}/export.json".format(domain)
    pipeline = DataPipeline(log_uri = s3_logs)
    pipeline.add_shell_command("ConsulBackup",
                               cmd,
                               destination = Ref("ConsulBucket"),
                               runs_on = Ref("ConsulInstance"))
    pipeline.add_ec2_instance("ConsulInstance", subnet=internal_subnet)
    pipeline.add_s3_bucket("ConsulBucket", s3_backup + "/consul")
    config.add_data_pipeline("ConsulBackupPipeline", "consul-backup."+domain, pipeline.objects)


    # DynamoDB Backup
    tables = {
        "BossMeta": names.meta,
        "S3Index": names.s3_index,
        "TileIndex": names.tile_index,
        "IdIndex": names.id_index,
        "IdCountIndex": names.id_count_index,
    }

    pipeline = DataPipeline(log_uri = s3_logs)
    pipeline.add_emr_cluster("BackupCluster")

    for name in tables:
        table = tables[name]
        pipeline.add_s3_bucket(name + "Bucket", s3_backup + "/DDB/" + table)
        pipeline.add_ddb_table(name, table)
        pipeline.add_emr_copy(name+"Copy", Ref(name), Ref(name + "Bucket"), Ref("BackupCluster"))

    config.add_data_pipeline("DDBPipeline", "dynamo-backup."+domain, pipeline.objects)


    # Endpoint RDS Backup
    print("Querying Endpoint DB credentials")
    with call.vault() as vault:
        db_config = vault.read(const.VAULT_ENDPOINT_DB)

        endpoint_user = db_config['user']
        endpoint_pass = db_config['password']

    pipeline = rds_copy(call, names.endpoint_db, 'boss', endpoint_user, endpoint_pass, internal_subnet, backup_image, s3_logs, s3_backup)
    config.add_data_pipeline("EndpointPipeline", "endpoint-backup."+domain, pipeline.objects)


    # Auth RDS Backup
    SCENARIO = os.environ["SCENARIO"]
    AUTH_DB = SCENARIO in ("production", "ha-development",)
    if AUTH_DB:
        pipeline = rds_copy(call, names.auth_db, 'keycloak', 'keycloak', 'keycloak', internal_subnet, backup_image, s3_logs, s3_backup)
        config.add_data_pipeline("AuthPipeline", "auth-backup."+domain, pipeline.objects)


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

def update(session, domain):
    config = create_config(session, domain)
    success = config.update(session)

    return success

def delete(session, domain):
    names = AWSNames(domain)

    resp = input("Delete all backup data [N/y] ")
    if len(resp) == 0 or resp[0] not in ('y', 'Y'):
        print("Not deleting stack")
        return

    CloudFormationConfiguration('backup', domain).delete(session)
    aws.s3_bucket_delete(session, 'backup.' + domain, empty=True)

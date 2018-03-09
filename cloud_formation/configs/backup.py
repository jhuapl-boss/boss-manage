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
from lib.vault import POLICY_DIR as VAULT_POLICY_DIR

import os

def rds_copy(rds_name, subnet, image, s3_logs, s3_backup):
    pipeline = DataPipeline(log_uri = s3_logs, resource_role="backup")
    pipeline.add_ec2_instance("RDSInstance",
                              subnet = subnet,
                              image = image)
    pipeline.add_s3_bucket("RDSBucket", s3_backup + "/RDS/" + rds_name)
    pipeline.add_shell_command("RDSBackup",
                               "bash ~/rds.sh backup {}".format(rds_name),
                               destination = Ref("RDSBucket"),
                               runs_on = Ref("RDSInstance"))
                               
    return pipeline

def create_config(session, domain):
    """Create the CloudFormationConfiguration object."""
    config = CloudFormationConfiguration('backup', domain, const.REGION)
    names = AWSNames(domain)

    internal_subnet = aws.subnet_id_lookup(session, names.internal)
    backup_image = aws.ami_lookup(session, 'backup.boss')[0]

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
    config.add_data_pipeline("ConsulBackupPipeline",
                             "consul-backup."+domain,
                             pipeline.objects,
                             depends_on = "BackupBucket")


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

    config.add_data_pipeline("DDBPipeline",
                             "dynamo-backup."+domain,
                             pipeline.objects,
                             depends_on = "BackupBucket")


    # Endpoint RDS Backup
    pipeline = rds_copy(names.endpoint_db, internal_subnet, backup_image, s3_logs, s3_backup)
    config.add_data_pipeline("EndpointPipeline",
                             "endpoint-backup."+domain,
                             pipeline.objects,
                             depends_on = "BackupBucket")


    # Auth RDS Backup
    SCENARIO = os.environ["SCENARIO"]
    AUTH_DB = SCENARIO in ("production", "ha-development",)
    if AUTH_DB:
        pipeline = rds_copy(names.auth_db, internal_subnet, backup_image, s3_logs, s3_backup)
        config.add_data_pipeline("AuthPipeline",
                                 "auth-backup."+domain,
                                 pipeline.objects,
                                 depends_on = "BackupBucket")


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
        post_init(session, domain)

def post_init(session, domain):
    keypair = aws.keypair_lookup(session)
    call = ExternalCalls(session, keypair, domain)

    with call.vault() as vault:
        name = "backup"
        #if name not in vault.list_policies():
        policy = "{}/{}.hcl".format(VAULT_POLICY_DIR, name)
        account_id = aws.get_account_id_from_session(session)
        policy_arn = 'arn:aws:iam::{}:instance-profile/{}'.format(account_id, name)
        with open(policy, 'r') as fh:
            vault.set_policy(name, fh.read())
            vault.write("/auth/aws-ec2/role/" + name,
                        policies = name,
                        bound_iam_role_arn = policy_arn)

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

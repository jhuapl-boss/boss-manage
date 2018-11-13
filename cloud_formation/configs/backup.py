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

def create_config(bosslet_config):
    """Create the CloudFormationConfiguration object."""
    config = CloudFormationConfiguration('backup', bosslet_config)
    names = bosslet_config.names

    # DP NOTE: During implementation there was/is an availability zone that
    #          could not run the T2.Micro instances used by this Data Pipeline
    azs = aws.azs_lookup(bosslet_config, 'datapipeline')
    az = random.choice(azs)[1] + '-'
    internal_subnet = aws.subnet_id_lookup(bosslet_config.session,
                                           az + bosslet_config.names.subnet.internal)
    backup_image = aws.ami_lookup(bosslet_config, names.ami.backup)[0]

    s3_backup = "s3://" + names.s3.backup + "/#{format(@scheduledStartTime, 'YYYY-ww')}"
    s3_logs = "s3://" + names.s3.backup + "/logs"

    # DP TODO: Create all BOSS S3 buckets as part of the account setup
    #          as the Cloud Formation delete doesn't delete the bucket,
    #          making this a conditional add
    BUCKET_DEPENDENCY = None # Needed as the pipelines try to execute when launched
    if not aws.s3_bucket_exists(session, names.s3.backup):
        life_cycle = {
            'Rules': [{
                'Id': 'Delete Data',
                'Status': 'Enabled',
                'ExpirationInDays': 180, # ~6 Months
            }]
        }
        encryption = {
            'ServerSideEncryptionConfiguration': [{
                'ServerSideEncryptionByDefault': {
                    'SSEAlgorithm': 'AES256'
                }
            }]
        }
        config.add_s3_bucket("BackupBucket",
                             names.s3.backup,
                             life_cycle_config=life_cycle,
                             encryption=encryption)
        BUCKET_DEPENDENCY = "BackupBucket"

    # Consul Backup
    # DP NOTE: Currently having issue with Consul restore, hence both Consul and Vault backups
    cmd = "/usr/local/bin/consulate --api-host {} kv backup -b -f ${{OUTPUT1_STAGING_DIR}}/export.json".format(names.dns.consul)
    pipeline = DataPipeline(log_uri = s3_logs, resource_role="backup")
    pipeline.add_shell_command("ConsulBackup",
                               cmd,
                               destination = Ref("ConsulBucket"),
                               runs_on = Ref("ConsulInstance"))
    pipeline.add_s3_bucket("ConsulBucket", s3_backup + "/consul")
    pipeline.add_ec2_instance("ConsulInstance",
                              subnet=internal_subnet,
                              image = backup_image)
    config.add_data_pipeline("ConsulBackupPipeline",
                             "consul-backup."+bosslet_config.INTERNAL_DOMAIN,
                             pipeline.objects,
                             depends_on = BUCKET_DEPENDENCY)

    # Vault Backup
    cmd = "/usr/local/bin/python3 ~/vault.py backup {}".format(bosslet_config.INTERNAL_DOMAIN)
    pipeline = DataPipeline(log_uri = s3_logs, resource_role="backup")
    pipeline.add_shell_command("VaultBackup",
                               cmd,
                               destination = Ref("VaultBucket"),
                               runs_on = Ref("VaultInstance"))
    pipeline.add_s3_bucket("VaultBucket", s3_backup + "/vault")
    pipeline.add_ec2_instance("VaultInstance",
                              subnet=internal_subnet,
                              image = backup_image)
    config.add_data_pipeline("VaultBackupPipeline",
                             "vault-backup."+bosslet_config.INTERNAL_DOMAIN,
                             pipeline.objects,
                             depends_on = BUCKET_DEPENDENCY)


    # DynamoDB Backup
    tables = {
        "BossMeta": names.ddb.meta,
        "S3Index": names.ddb.s3_index,
        "TileIndex": names.ddb.tile_index,
        "IdIndex": names.ddb.id_index,
        "IdCountIndex": names.ddb.id_count_index,
    }

    pipeline = DataPipeline(log_uri = s3_logs)
    pipeline.add_emr_cluster("BackupCluster", region = bosslet_config.REGION)

    for name in tables:
        table = tables[name]
        pipeline.add_s3_bucket(name + "Bucket", s3_backup + "/DDB/" + table)
        pipeline.add_ddb_table(name, table)
        pipeline.add_emr_copy(name+"Copy",
                              Ref(name),
                              Ref(name + "Bucket"),
                              runs_on = Ref("BackupCluster"),
                              region = bosslet_config.REGION)

    config.add_data_pipeline("DDBPipeline",
                             "dynamo-backup."+bosslet_config.INTERNAL_DOMAIN,
                             pipeline.objects,
                             depends_on = BUCKET_DEPENDENCY)


    # Endpoint RDS Backup
    pipeline = rds_copy(names.rds.endpoint_db, internal_subnet, backup_image, s3_logs, s3_backup)
    config.add_data_pipeline("EndpointPipeline",
                             "endpoint-backup."+bosslet_config.INTERNAL_DOMAIN,
                             pipeline.objects,
                             depends_on = BUCKET_DEPENDENCY)


    # Auth RDS Backup
    if bosslet_config.AUTH_RDS:
        pipeline = rds_copy(names.rds.auth_db, internal_subnet, backup_image, s3_logs, s3_backup)
        config.add_data_pipeline("AuthPipeline",
                                 "auth-backup."+bosslet_config.INTERNAL_DOMAIN,
                                 pipeline.objects,
                                 depends_on = BUCKET_DEPENDENCY)


    return config

def generate(bosslet_config):
    config = create_config(bosslet_config)
    config.generate()

def create(bosslet_config):
    config = create_config(bosslet_config)

    config.create()

    post_init(bosslet_config)

def post_init(bosslet_config):
    # DP NOTE: For an existing stack the backup policy,
    #          aws login, and keycloak RDS credentials
    #          need to be configured in Vault
    #
    #          At some point this code can be deprecated and eventually removed
    with bosslet_config.call.vault() as vault:
        name = "backup"
        if name not in vault.list_policies(): # only update if needed
            policy = "{}/{}.hcl".format(VAULT_POLICY_DIR, name)
            policy_arn = 'arn:aws:iam::{}:instance-profile/{}'.format(bosslet_config.ACCOUNT_ID, name)

            with open(policy, 'r') as fh:
                vault.set_policy(name, fh.read()) # Create Vault Policy

            vault.write("/auth/aws/role/" + name, # Create AWS login
                        auth_type = 'ec2',
                        policies = name,
                        bound_iam_role_arn = policy_arn)

            vault.write(const.VAULT_KEYCLOAK_DB,  # Create Keycloak RDS credentials
                        name = "keycloak",
                        user = "keycloak",
                        password = "keycloak")
        else:
            print("Vault already configured to provide AWS credentials for backup/restore")

def update(bosslet_config):
    config = create_config(bosslet_config)
    success = config.update()

def delete(bosslet_config):
    config = CloudFormationConfiguration('backup', bosslet_config)
    config.delete()

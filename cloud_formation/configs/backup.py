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

    # XXX: AZ `E` is incompatible with T2.Micro instances (used by backup)
    internal_subnet = aws.subnet_id_lookup(session, 'b-' + names.internal)
    backup_image = aws.ami_lookup(session, 'backup.boss')[0]

    s3_backup = "s3://backup." + domain + "/#{format(@scheduledStartTime, 'YYYY-ww')}"
    s3_logs = "s3://backup." + domain + "/logs"

    # DP TODO: Create all BOSS S3 buckets as part of the account setup
    #          as the Cloud Formation delete doesn't delete the bucket,
    #          making this a conditional add
    BUCKET_DEPENDENCY = None # Needed as the pipelines try to execute when launched
    if not aws.s3_bucket_exists(session, "backup." + domain):
        life_cycle = {
            'Rules': [{
                'Id': 'Delete Data',
                'Status': 'Enabled',
                'ExpirationInDays': 180, # ~6 Months
            }]
        }
        config.add_s3_bucket("BackupBucket",
                             "backup." + domain,
                             life_cycle_config=life_cycle)
        BUCKET_DEPENDENCY = "BackupBucket"

    # Consul Backup
    # DP NOTE: Currently having issue with Consul restore, hence both Consul and Vault backups
    cmd = "/usr/local/bin/consulate --api-host consul.{} kv backup -b -f ${{OUTPUT1_STAGING_DIR}}/export.json".format(domain)
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
                             "consul-backup."+domain,
                             pipeline.objects,
                             depends_on = BUCKET_DEPENDENCY)

    # Vault Backup
    cmd = "/usr/local/bin/python3 ~/vault.py backup {}".format(domain)
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
                             "vault-backup."+domain,
                             pipeline.objects,
                             depends_on = BUCKET_DEPENDENCY)


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
                             depends_on = BUCKET_DEPENDENCY)


    # Endpoint RDS Backup
    pipeline = rds_copy(names.endpoint_db, internal_subnet, backup_image, s3_logs, s3_backup)
    config.add_data_pipeline("EndpointPipeline",
                             "endpoint-backup."+domain,
                             pipeline.objects,
                             depends_on = BUCKET_DEPENDENCY)


    # Auth RDS Backup
    SCENARIO = os.environ["SCENARIO"]
    AUTH_DB = SCENARIO in ("production", "ha-development",)
    if AUTH_DB:
        pipeline = rds_copy(names.auth_db, internal_subnet, backup_image, s3_logs, s3_backup)
        config.add_data_pipeline("AuthPipeline",
                                 "auth-backup."+domain,
                                 pipeline.objects,
                                 depends_on = BUCKET_DEPENDENCY)


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

    # DP NOTE: For an existing stack the backup policy,
    #          aws-ec2 login, and keycloak RDS credentials
    #          need to be configured in Vault
    #
    #          At some point this code can be deprecated and eventually removed
    with call.vault() as vault:
        name = "backup"
        if name not in vault.list_policies(): # only update if needed
            policy = "{}/{}.hcl".format(VAULT_POLICY_DIR, name)
            account_id = aws.get_account_id_from_session(session)
            policy_arn = 'arn:aws:iam::{}:instance-profile/{}'.format(account_id, name)

            with open(policy, 'r') as fh:
                vault.set_policy(name, fh.read()) # Create Vault Policy

            vault.write("/auth/aws-ec2/role/" + name, # Create AWS-EC2 login
                        policies = name,
                        bound_iam_role_arn = policy_arn)

            vault.write(const.VAULT_KEYCLOAK_DB,  # Create Keycloak RDS credentials
                        name = "keycloak",
                        user = "keycloak",
                        password = "keycloak")
        else:
            print("Vault already configured to provide AWS credentials for backup/restore")

def update(session, domain):
    config = create_config(session, domain)
    success = config.update(session)

    return success

def delete(session, domain):
    CloudFormationConfiguration('backup', domain).delete(session)

#!/usr/bin/env python3

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

"""A driver script for creating AWS CloudFormation Stacks."""

import argparse
import sys
import os

import alter_path
from lib import aws
from lib import constants as const
from lib.names import AWSNames
from lib.external import ExternalCalls
from lib.datapipeline import DataPipeline, Ref

def list_s3_bucket(session, bucket, prefix):
    client = session.client('s3')

    prefix += '/'
    resp = client.list_objects_v2(Bucket = bucket, Prefix = prefix, Delimiter = '/')
    dirs = [cp['Prefix'].replace(prefix, '', 1)[:-1] for cp in resp.get('CommonPrefixes',[])]
    print(dirs)
    return dirs
    #for content in resp['Contents']:
    #    print(content['Key'])

def consul_pipeline(session, domain, directory):
    names = AWSNames(domain)
    internal_subnet = aws.subnet_id_lookup(session, names.internal)

    s3_backup = "s3://backup." + domain + "/" + directory
    s3_log = "s3://backup." + domain + "/restore-logs/"

    pipeline = DataPipeline(fmt="DP", log_uri = s3_log)
    pipeline.add_shell_command("ConsulBackup",
                               "python -c \"import json, requests; [requests.put('http://consul.{}:8500/v1/kv'+i['Key'], i['Value'])  for i in json.load(open('${{INPUT1_STAGING_DIR}}/export.json'))]\"".format(domain),
                               source = Ref("ConsulBucket"),
                               runs_on = Ref("ConsulInstance"))
    pipeline.add_ec2_instance("ConsulInstance",
                              subnet = internal_subnet,
                              image = aws.ami_lookup(session, "backup.boss-test")[0])
    pipeline.add_s3_bucket("ConsulBucket", s3_backup + "/consul")
    return pipeline

def ddb_pipeline(session, domain, directory):
    s3_backup = "s3://backup." + domain + "/" + directory
    s3_log = "s3://backup." + domain + "/restore-logs/"

    pipeline = DataPipeline(fmt="DP", log_uri = s3_log)
    pipeline.add_emr_cluster("BackupCluster")

    tables = list_s3_bucket(session, "backup." + domain, directory + "/DDB")
    for table in tables:
        name = table.split('.', 1)[0]
        pipeline.add_s3_bucket(name + "Bucket", s3_backup + "/DDB/" + table)
        pipeline.add_ddb_table(name, table)
        pipeline.add_emr_copy(name+"Copy", Ref(name + "Bucket"), Ref(name), Ref("BackupCluster"), export=False)

    return pipeline

def rds_pipeline(session, domain, directory, component, rds_name, db_name, db_user, db_pass):
    names = AWSNames(domain)
    subnet = aws.subnet_id_lookup(session, names.internal)

    s3_backup = "s3://backup." + domain + "/" + directory
    s3_log = "s3://backup." + domain + "/restore-logs/"


    tables = list_s3_bucket(session, "backup." + domain, directory + "/RDS/" + db_name)
    if len(tables) == 0:
        print("No {} tables backed up on {}, skipping restore".format(component, directory))
        #return None

    cmd = "mysql --host {} --user {} --password={} {} < ${{INPUT1_STAGING_DIR}}/{}.sql"
    cmd = cmd.format(rds_name, db_user, db_pass, db_name, db_name)

    pipeline = DataPipeline(fmt="DP", log_uri = s3_log)
    pipeline.add_shell_command("RDSBackup",
                               cmd,
                               source = Ref("RDSBucket"),
                               runs_on = Ref("RDSInstance"))
    pipeline.add_ec2_instance("RDSInstance",
                              subnet = subnet,
                              image = aws.ami_lookup(session, "backup.boss-test")[0])
    pipeline.add_s3_bucket("RDSBucket", s3_backup + "/RDS/" + db_name)
    """
    pipeline.add_ec2_instance(component + "Instance", subnet=subnet)
    pipeline.add_rds_database(component + "DB",
                              # The instance name is the DNS name without '.',
                              rds_name.replace('.', '-'),
                              db_user,
                              db_pass)
    for table in tables:
        name = component + "-" + table.capitalize()
        pipeline.add_s3_bucket(name + "Bucket", s3_backup + "/RDS/" + db_name + "/" + table)

        pipeline.add_rds_table(name, Ref(component + "DB"), table)
        pipeline.add_rds_copy(name+"Copy", Ref(name+"Bucket"), Ref(name), Ref(component + "Instance"))
    """

    return pipeline

def endpoint_rds_pipeline(session, domain, directory):
    names = AWSNames(domain)
    keypair = aws.keypair_lookup(session)
    call = ExternalCalls(session, keypair, domain)

    print("Querying Endpoint DB credentials")
    with call.vault() as vault:
        db_config = vault.read(const.VAULT_ENDPOINT_DB)

        endpoint_user = db_config['user']
        endpoint_pass = db_config['password']

    return rds_pipeline(session,
                        domain,
                        directory,
                        "Endpoint",
                        names.endpoint_db,
                        'boss',
                        endpoint_user,
                        endpoint_pass)

def auth_rds_pipeline(session, domain, directory):
    names = AWSNames(domain)

    return rds_pipeline(session,
                        domain,
                        directory,
                        "Auth",
                        names.auth_db,
                        'keycloak',
                        'keycloak',
                        'keycloak')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = "Script the restoration of a backup")
    parser.add_argument("--aws-credentials", "-a",
                        metavar = "<file>",
                        default = os.environ.get("AWS_CREDENTIALS"),
                        type = argparse.FileType('r'),
                        help = "File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("domain_name", help="Domain in which to execute the configuration (example: subnet.vpc.boss)")
    parser.add_argument("backup_date", help="Year and week of the backup to restore (format: YYYY-ww")

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    session = aws.create_session(args.aws_credentials)

    pipeline_ids = []
    pipeline_args = (session, args.domain_name, args.backup_date)
    print("Creating and activating restoration data pipelines")
    for name, pipeline in [('consul', consul_pipeline(*pipeline_args)),
                           ('dynamo', ddb_pipeline(*pipeline_args)),
                           ('endpoint', endpoint_rds_pipeline(*pipeline_args)),
                           ('auth', auth_rds_pipeline(*pipeline_args))]:
        if pipeline is None:
            continue

        id = aws.create_data_pipeline(session,
                                      name + '-restore.' + args.domain_name,
                                      pipeline)
        if id is None:
            print("Problem creating {} pipeline, cannot restore".format(name))
            continue

        aws.activate_data_pipeline(session, id)
        pipeline_ids.append(id)

    print("Pipelines all activated, waiting for restore to finish...")
    # Cannot currently find a method to query pipeline execution status that will
    # tell us when they are finished
    input("Press any key to delete pipelines")

    for id in pipeline_ids:
        aws.delete_data_pipeline(session, id)

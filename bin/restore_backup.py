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

"""
A script that manually creates Data Pipelines to restore a backup
"""

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
    files = [c['Key'].replace(prefix, '', 1) for c in resp.get('Contents', [])]

    return dirs, files

def consul_pipeline(session, domain, directory):
    # DP NOTE: Currently having issues with Consul restore
    #          For a restore certain kv paths shouldn't be restored
    #          and all Vault instances must be shutdown, so they are not
    #          interacting with Consul during the restore
    #
    # See
    # https://groups.google.com/forum/#!msg/vault-tool/nTj0V9hC31E/0VT3Qq_CDQAJ
    # https://groups.google.com/forum/#!msg/vault-tool/ISCbNmQVXms
    names = AWSNames(domain)
    # XXX: AZ `E` is incompatible with T2.Micro instances (used by backup)
    internal_subnet = aws.subnet_id_lookup(session, 'b-' + names.internal)

    s3_backup = "s3://backup." + domain + "/" + directory
    s3_log = "s3://backup." + domain + "/restore-logs/"
    cmd = "/usr/local/bin/consulate --api-host consul.{} kv restore -b -f ${{INPUT1_STAGING_DIR}}/export.json".format(domain)

    _, data = list_s3_bucket(session, "backup." + domain, directory + "/vault")
    if len(data) == 0:
        print("No consul data backed up on {}, skipping restore".format(directory))
        return None

    pipeline = DataPipeline(fmt="DP", log_uri = s3_log, resource_role="backup")
    pipeline.add_shell_command("ConsulRestore",
                               cmd,
                               source = Ref("ConsulBucket"),
                               runs_on = Ref("ConsulInstance"))
    pipeline.add_ec2_instance("ConsulInstance",
                              subnet = internal_subnet,
                              image = aws.ami_lookup(session, "backup.boss")[0])
    pipeline.add_s3_bucket("ConsulBucket", s3_backup + "/consul")
    return pipeline

def vault_pipeline(session, domain, directory):
    names = AWSNames(domain)
    # XXX: AZ `E` is incompatible with T2.Micro instances (used by backup)
    internal_subnet = aws.subnet_id_lookup(session, 'b-' + names.internal)

    s3_backup = "s3://backup." + domain + "/" + directory
    s3_log = "s3://backup." + domain + "/restore-logs/"
    cmd = "/usr/local/bin/python3 ~/vault.py restore {}".format(domain)

    _, data = list_s3_bucket(session, "backup." + domain, directory + "/vault")
    if len(data) == 0:
        print("No vault data backed up on {}, skipping restore".format(directory))
        return None

    pipeline = DataPipeline(fmt="DP", log_uri = s3_log, resource_role="backup")
    pipeline.add_shell_command("VaultRestore",
                               cmd,
                               source = Ref("VaultBucket"),
                               runs_on = Ref("VaultInstance"))
    pipeline.add_ec2_instance("VaultInstance",
                              subnet = internal_subnet,
                              image = aws.ami_lookup(session, "backup.boss")[0])
    pipeline.add_s3_bucket("VaultBucket", s3_backup + "/vault")
    return pipeline

def ddb_delete_data(session, table_name):
    response = None

    ddb = session.resource('dynamodb')
    tbl = ddb.Table(table_name)

    print("Deleting data in {} table".format(table_name))

    # Get the current schema keys for the table
    keys = [k['AttributeName'] for k in tbl.key_schema]

    while response is None or 'LastEvaluatedKey' in response:
        if response is None:
            response = tbl.scan()
        else:
            response = tbl.scan(ExclusiveStartKey = response['LastEvaluatedKey'])

        for item in response['Items']:
            # calculate the key for the item, ignoring data elements
            key = { k: v for k,v in item.items() if k in keys }
            tbl.delete_item(Key = key)

def ddb_pipeline(session, domain, directory):
    s3_backup = "s3://backup." + domain + "/" + directory
    s3_log = "s3://backup." + domain + "/restore-logs/"

    pipeline = DataPipeline(fmt="DP", log_uri = s3_log)
    pipeline.add_emr_cluster("RestoreCluster")

    tables, _ = list_s3_bucket(session, "backup." + domain, directory + "/DDB")
    for table in tables:
        name = table.split('.', 1)[0]
        pipeline.add_s3_bucket(name + "Bucket", s3_backup + "/DDB/" + table)
        pipeline.add_ddb_table(name, table)
        pipeline.add_emr_copy(name+"Copy",
                              Ref(name + "Bucket"),
                              Ref(name),
                              Ref("RestoreCluster"),
                              export=False)

    for table in tables:
        name = table.split('.', 1)[0]
        resp = input("Delete existing data in {}? [y/N] ".format(name))
        if resp and len(resp) > 0 and resp[0].lower() == 'y':
            ddb_delete_data(session, table)

    return pipeline

def rds_pipeline(session, domain, directory, component, rds_name):
    names = AWSNames(domain)
    # XXX: AZ `E` is incompatible with T2.Micro instances (used by backup)
    subnet = aws.subnet_id_lookup(session, 'b-' + names.internal)

    s3_backup = "s3://backup." + domain + "/" + directory
    s3_log = "s3://backup." + domain + "/restore-logs/"


    _, data = list_s3_bucket(session, "backup." + domain, directory + "/RDS/" + rds_name)
    if len(data) == 0:
        print("No {} table data backed up on {}, skipping restore".format(component, directory))
        return None

    pipeline = DataPipeline(fmt="DP", log_uri = s3_log, resource_role="backup")
    pipeline.add_shell_command("RDSRestore",
                               "bash ~/rds.sh restore {}".format(rds_name),
                               source = Ref("RDSBucket"),
                               runs_on = Ref("RDSInstance"))
    pipeline.add_ec2_instance("RDSInstance",
                              subnet = subnet,
                              image = aws.ami_lookup(session, "backup.boss")[0])
    pipeline.add_s3_bucket("RDSBucket", s3_backup + "/RDS/" + rds_name)

    return pipeline

def endpoint_rds_pipeline(session, domain, directory):
    names = AWSNames(domain)

    return rds_pipeline(session,
                        domain,
                        directory,
                        "Endpoint",
                        names.endpoint_db)

def auth_rds_pipeline(session, domain, directory):
    names = AWSNames(domain)

    return rds_pipeline(session,
                        domain,
                        directory,
                        "Auth",
                        names.auth_db)

if __name__ == '__main__':
    types = ['consul', 'vault', 'dynamo', 'endpoint', 'auth']
    parser = argparse.ArgumentParser(description = "Script the restoration of a backup")
    parser.add_argument("--aws-credentials", "-a",
                        metavar = "<file>",
                        default = os.environ.get("AWS_CREDENTIALS"),
                        type = argparse.FileType('r'),
                        help = "File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("--ami-version",
                        metavar = "<ami-version>",
                        default = "latest",
                        help = "The AMI version to use when selecting images (default: latest)")
    parser.add_argument("domain_name", help="Domain in which to execute the configuration (example: subnet.vpc.boss)")
    parser.add_argument("backup_date", help="Year and week of the backup to restore (format: YYYY-ww")
    parser.add_argument("type",
                        metavar = "<type>",
                        nargs = '*',
                        default = types,
                        help = "Type(s) of data to restore (choices: {})".format("|".join(types)))

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)
    if args.type:
        for t in args.type:
            if t not in types:
                parser.print_usage()
                print("Error: <type> can only include ({})".format("|".join(types)))
                sys.exit(1)

    os.environ["AMI_VERSION"] = args.ami_version
    session = aws.create_session(args.aws_credentials)

    pipeline_ids = []
    pipeline_args = (session, args.domain_name, args.backup_date)
    print("Creating and activating restoration data pipelines")
    for name, build in [
                        # Currently having issues with Consul restore
                        #('consul', consul_pipeline),

                        # NOTE: in some scenarios vault data may need to be be
                        #       restored before the other restores are executed
                        ('vault', vault_pipeline),

                        ('dynamo', ddb_pipeline),
                        ('endpoint', endpoint_rds_pipeline),
                        ('auth', auth_rds_pipeline)
                       ]:
        if name not in args.type:
            continue

        pipeline = build(*pipeline_args)
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

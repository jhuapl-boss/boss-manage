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

import sys
import os
import random

import alter_path
from lib import aws
from lib.datapipeline import DataPipeline, Ref
from lib.configuration import BossParser

def list_s3_bucket(session, bucket, prefix):
    client = session.client('s3')

    prefix += '/'
    resp = client.list_objects_v2(Bucket = bucket, Prefix = prefix, Delimiter = '/')

    dirs = [cp['Prefix'].replace(prefix, '', 1)[:-1] for cp in resp.get('CommonPrefixes',[])]
    files = [c['Key'].replace(prefix, '', 1) for c in resp.get('Contents', [])]

    return dirs, files

def subnet_id_lookup(bosslet_config):
    # DP NOTE: During implementation there was/is an availability zone that
    #          could not run the T2.Micro instances used by this Data Pipeline
    azs = aws.azs_lookup(bosslet_config, 'datapipeline')
    az = random.choice(azs)[1] + '-'

    internal_subnet = aws.subnet_id_lookup(bosslet_config.session,
                                           az + bosslet_config.names.internal.subnet)
    return internal_subnet

def vault_pipeline(bosslet_config, directory):
    internal_subnet = subnet_id_lookup(bosslet_config)

    names = bosslet_config.names
    s3_backup = "s3://" + names.backup.s3 + "/" + directory
    s3_log = "s3://" + names.backup.s3 + "/restore-logs/"
    cmd = "/usr/local/bin/python3 ~/vault.py restore {}".format(bosslet_config.INTERNAL_DOMAIN)

    _, data = list_s3_bucket(bosslet_config.session, names.backup.s3, directory + "/vault")
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
                              image = aws.ami_lookup(bosslet_config, names.backup.ami)[0])
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

def ddb_pipeline(bosslet_config, directory):
    names = bosslet_config.names
    s3_backup = "s3://" + names.backup.s3 + "/" + directory
    s3_log = "s3://" + names.backup.s3 + "/restore-logs/"

    pipeline = DataPipeline(fmt="DP", log_uri = s3_log)
    pipeline.add_emr_cluster("RestoreCluster", region = bosslet_config.REGION)

    tables, _ = list_s3_bucket(bosslet_config.session, names.backup.s3, directory + "/DDB")
    for table in tables:
        name = table.split('.', 1)[0]
        if name == 'vault':
            name = 'VaultData'
        pipeline.add_s3_bucket(name + "Bucket", s3_backup + "/DDB/" + table)
        pipeline.add_ddb_table(name, table)
        pipeline.add_emr_copy(name+"Copy",
                              Ref(name + "Bucket"),
                              Ref(name),
                              runs_on = Ref("RestoreCluster"),
                              region = bosslet_config.REGION,
                              export=False)

    for table in tables:
        name = table.split('.', 1)[0]
        resp = input("Delete existing data in {} table? [y/N] ".format(name))
        if resp and len(resp) > 0 and resp[0].lower() == 'y':
            ddb_delete_data(bosslet_config.session, table)

    return pipeline

def rds_pipeline(bosslet_config, directory, component, rds_name):
    names = bosslet_config.names
    subnet = subnet_id_lookup(bosslet_config)

    s3_backup = "s3://" + names.backup.s3 + "/" + directory
    s3_log = "s3://" + names.backup.s3 + "/restore-logs/"


    _, data = list_s3_bucket(bosslet_config.session, names.backup.s3, directory + "/RDS/" + rds_name)
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
                              image = aws.ami_lookup(bosslet_config, names.backup.ami)[0])
    pipeline.add_s3_bucket("RDSBucket", s3_backup + "/RDS/" + rds_name)

    return pipeline

def endpoint_rds_pipeline(bosslet_config, directory):
    return rds_pipeline(bosslet_config,
                        directory,
                        "Endpoint",
                        bosslet_config.names.endpoint_db.rds)

def auth_rds_pipeline(bosslet_config, directory):
    return rds_pipeline(bosslet_config,
                        directory,
                        "Auth",
                        bosslet_config.names.auth_db.rds)

if __name__ == '__main__':
    types = ['vault', 'dynamo', 'endpoint', 'auth']
    parser = BossParser(description = "Script the restoration of a backup")
    parser.add_argument("--ami-version",
                        metavar = "<ami-version>",
                        default = "latest",
                        help = "The AMI version to use when selecting images (default: latest)")
    parser.add_bosslet()
    parser.add_argument("backup_date", help="Year and week of the backup to restore (format: YYYY-ww")
    parser.add_argument("type",
                        metavar = "<type>",
                        nargs = '*',
                        default = types,
                        help = "Type(s) of data to restore (choices: {})".format("|".join(types)))

    args = parser.parse_args()
    bosslet_config = args.bosslet_config

    if args.type:
        for t in args.type:
            if t not in types:
                parser.print_usage()
                print("Error: <type> can only include ({})".format("|".join(types)))
                sys.exit(1)

    bosslet_config.ami_version = args.ami_version

    pipeline_ids = []
    pipeline_args = (bosslet_config, args.backup_date)
    print("Creating and activating restoration data pipelines")
    for name, build in [
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

        id = aws.create_data_pipeline(bosslet_config.session,
                                      name + '-restore.' + bosslet_config.INTERNAL_DOMAIN
                                      pipeline)
        if id is None:
            print("Problem creating {} pipeline, cannot restore".format(name))
            continue

        aws.activate_data_pipeline(bosslet_config.session, id)
        pipeline_ids.append(id)

    print("Pipelines all activated, waiting for restore to finish...")
    # Cannot currently find a method to query pipeline execution status that will
    # tell us when they are finished
    input("Press any key to delete pipelines, after verifying that they have finished")

    for id in pipeline_ids:
        aws.delete_data_pipeline(bosslet_config.session, id)

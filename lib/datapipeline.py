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

"""Configuration class and supporting classes for building Data Pipeline
templates for CloudFormation.

Author:
    Derek Pryor <Derek.Pryor@jhuapl.edu>
"""

from . import constants as const

class Ref(object):
    def __init__(self, ref):
        self.ref = ref

    def __str__(self):
        return self.ref

def field_key(key):
    if key == "password":
        return "*password"
    else:
        return key

def field_type(value):
    if isinstance(value, Ref):
        return "RefValue"
    else:
        return "StringValue"

def field_value(value):
    if isinstance(value, Ref):
        return value.ref
    else:
        return value

class DataPipeline(object):
    def __init__(self, role="DataPipelineDefaultRole", resource_role="DataPipelineDefaultResourceRole", log_uri=None, fmt="CF"):
        self.fmt = fmt
        self.objects = []

        """
        {
            "id": "DefaultSchedule",
            "name": "Every 1 day",
            "type": "Schedule",
            "period": "1 days",
            "startAt": "FIRST_ACTIVATION_DATE_TIME"
        },
        """
        self.add_field("DefaultSchedule",
                       "DefaultSchedule",
                       type = "Schedule",
                       period = "1 weeks",
                       startAt = "FIRST_ACTIVATION_DATE_TIME")

        """
        {
          "failureAndRerunMode": "CASCADE",
          "schedule": {
            "ref": "DefaultSchedule"
          },
          "resourceRole": "DataPipelineDefaultResourceRole",
          "role": "DataPipelineDefaultRole",
          "scheduleType": "cron",
          "name": "Default",
          "id": "Default"
        },
        """
        self.add_field("Default",
                       "Default",
                       type = "Default",
                       schedule = Ref("DefaultSchedule"),
                       pipelineLogUri = log_uri,
                       failureAndRerunMode = "CASCADE",
                       resourceRole = resource_role,
                       role = role,
                       scheduleType = "cron")

    def add_field(self, id, name, **fields):
        def key_(k):
            if self.fmt != "CF":
                k = k[0].lower() + k[1:]
            return k

        field = {
            key_("Id"): id,
            key_("Name"): name,
            key_("Fields"): [
                { key_("Key"): field_key(key),
                  key_(field_type(value)): field_value(value)}
                for key, value in fields.items() if value # not None
            ],
        }

        self.objects.append(field)

    def add_ec2_instance(self, name, type="t1.micro", sgs=None, subnet=None, duration="2 Hours", image=None):
        """
        {
            "id": "Ec2Instance",
            "name": "Ec2Instance",
            "type": "Ec2Resource",
            "instanceType": "#{myEC2InstanceType}",
            "actionOnTaskFailure": "terminate",
            "securityGroups": "#{myEc2RdsSecurityGrps}",
            "terminateAfter": "2 Hours"
        },
        """

        self.add_field(name,
                       name,
                       type = "Ec2Resource",
                       instanceType = type,
                       actionOnTaskFailure = "terminate",
                       securityGroupIds = sgs,
                       subnetId = subnet,
                       imageId = image,
                       keyPair = "pryordm1-test",
                       terminateAfter = duration)

    def add_emr_cluster(self, name, type="m3.xlarge", count="1", version="3.9.0", region=None, duration="2 Hours"):
        """
        {
            "id": "EmrClusterForBackup",
            "name": "EmrClusterForBackup",
            "type": "EmrCluster"
            "bootstrapAction": "
                s3://#{myDDBRegion}.elasticmapreduce/bootstrap-actions/configure-hadoop, 
                --yarn-key-value,yarn.nodemanager.resource.memory-mb=11520,
                --yarn-key-value,yarn.scheduler.maximum-allocation-mb=11520,
                --yarn-key-value,yarn.scheduler.minimum-allocation-mb=1440,
                --yarn-key-value,yarn.app.mapreduce.am.resource.mb=2880,
                --mapred-key-value,mapreduce.map.memory.mb=5760,
                --mapred-key-value,mapreduce.map.java.opts=-Xmx4608M,
                --mapred-key-value,mapreduce.reduce.memory.mb=2880,
                --mapred-key-value,mapreduce.reduce.java.opts=-Xmx2304m,
                --mapred-key-value,mapreduce.map.speculative=false",
            "coreInstanceCount": "1",
            "coreInstanceType": "m3.xlarge",
            "amiVersion": "3.9.0",
            "masterInstanceType": "m3.xlarge",
            "region": "#{myDDBRegion}",
        }
        """
        if region is None:
            region = const.REGION

        bootstrapArgs = """
s3://{}.elasticmapreduce/bootstrap-actions/configure-hadoop,
--yarn-key-value,yarn.nodemanager.resource.memory-mb=11520,
--yarn-key-value,yarn.scheduler.maximum-allocation-mb=11520,
--yarn-key-value,yarn.scheduler.minimum-allocation-mb=1440,
--yarn-key-value,yarn.app.mapreduce.am.resource.mb=2880,
--mapred-key-value,mapreduce.map.memory.mb=5760,
--mapred-key-value,mapreduce.map.java.opts=-Xmx4608M,
--mapred-key-value,mapreduce.reduce.memory.mb=2880,
--mapred-key-value,mapreduce.reduce.java.opts=-Xmx2304m,
--mapred-key-value,mapreduce.map.speculative=false
""".replace("\n", "").format(region)

        self.add_field(name,
                       name,
                       type = "EmrCluster",
                       bootstrapAction = bootstrapArgs,
                       coreInstanceCount = str(count),
                       coreInstanceType = type,
                       amiVersion = version,
                       masterInstanceType = type,
                       region = region,
                       terminateAfter = duration)

    def add_rds_database(self, name, instance, username, password):
        """
        {
            "id": "rds_mysql",
            "name": "rds_mysql",
            "type": "RdsDatabase",
            "jdbcProperties": "allowMultiQueries=true",
            "*password": "#{*myRDSPassword}",
            "rdsInstanceId": "#{myRDSInstanceId}",
            "username": "#{myRDSUsername}"
        },
        """
        self.add_field(name,
                       name,
                       type = "RdsDatabase",
                       jdbcProperties = "allowMultiQueries=true",
                       rdsInstanceId = instance,
                       username = username,
                       password = password)

    def add_rds_table(self, name, database, table):
        """
        {
            "id": "SourceRDSTable",
            "name": "SourceRDSTable",
            "type": "SqlDataNode",
            "database": {
                "ref": "rds_mysql"
            },
            "table": "#{myRDSTableName}",
            "selectQuery": "select * from #{table}"
        },
        """
        self.add_field(name,
                       name,
                       type = "SqlDataNode",
                       database = database,
                       table = table,
                       selectQuery = "select * from #{table}")

    def add_ddb_table(self, name, table, read_percent="0.25", write_percent="0.25"):
        """
        {
            "id": "DDBSourceTable",
            "name": "DDBSourceTable",
            "type": "DynamoDBDataNode",
            "readThroughputPercent": "#{myDDBReadThroughputRatio}",
            "tableName": "#{myDDBTableName}"
        },
        """
        self.add_field(name,
                       name,
                       type = "DynamoDBDataNode",
                       readThroughputPercent = read_percent,
                       writeThroughputPercent = write_percent,
                       tableName = table)

    def add_s3_bucket(self, name, s3_directory):
        """
        {
            "id": "S3OutputLocation",
            "name": "S3OutputLocation",
            "type": "S3DataNode"
            "directoryPath": "#{myOutputS3Loc}/#{format(@scheduledStartTime, 'YYYY-MM-dd-HH-mm-ss')}",
        }
        """
        self.add_field(name,
                       name,
                       type = "S3DataNode",
                       directoryPath = s3_directory)

    def add_rds_copy(self, name, source, destination, runs_on=None):
        """
        {
            "id": "RDStoS3CopyActivity",
            "name": "RDStoS3CopyActivity",
            "type": "CopyActivity"
            "output": {
                "ref": "S3OutputLocation"
            },
            "input": {
                "ref": "SourceRDSTable"
            },
            "runsOn": {
                "ref": "Ec2Instance"
            },
        },
        """
        self.add_field(name,
                       name,
                       type = "CopyActivity",
                       input = source,
                       output = destination,
                       runsOn = runs_on)

    def add_emr_copy(self, name, source, destination, runs_on=None, region=None, export=True):
        """
        {
            "id": "TableBackupActivity",
            "name": "TableBackupActivity",
            "type": "EmrActivity",
            "input": {
                "ref": "DDBSourceTable"
            },
            "output": {
                "ref": "S3BackupLocation"
            },
            "runsOn": {
                "ref": "EmrClusterForBackup"
            },
            "maximumRetries": "2",
            "step": "
                s3://dynamodb-emr-#{myDDBRegion}/emr-ddb-storage-handler/2.1.0/emr-ddb-2.1.0.jar,
                    org.apache.hadoop.dynamodb.tools.DynamoDbExport,
                    #{output.directoryPath},
                    #{input.tableName},
                    #{input.readThroughputPercent}",
            "resizeClusterBeforeRunning": "true"
        },
        """

        if region is None:
            region = const.REGION

        

        step = "s3://dynamodb-emr-{region}/emr-ddb-storage-handler/2.1.0/emr-ddb-2.1.0.jar,org.apache.hadoop.dynamodb.tools.DynamoDb{port},#{{{dir_type}.directoryPath}},#{{{tbl_type}.tableName}},#{{{rate}ThroughputPercent}}".format(
            region = region,
            port = "Export" if export else "Import",
            dir_type = "output" if export else "input",
            tbl_type = "input" if export else "output",
            rate = "input.read" if export else "output.write",
        )

        self.add_field(name,
                       name,
                       type = "EmrActivity",
                       input = source,
                       output = destination,
                       runsOn = runs_on,
                       maximumRetries = "2",
                       step = step,
                       resizeClusterBeforeRunning = "true")

    def add_shell_command(self, name, command, source=None, destination=None, runs_on=None):
        self.add_field(name,
                       name,
                       type = "ShellCommandActivity",
                       input = source,
                       output = destination,
                       runsOn = runs_on,
                       stage = "true",
                       command = command)

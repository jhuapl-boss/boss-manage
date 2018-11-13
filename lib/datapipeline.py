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

class Ref(object):
    """Reference internal to the Data Pipeline"""
    def __init__(self, ref):
        self.ref = ref

    def __str__(self):
        return self.ref

def field_key(key):
    """Create the correct key for a field
    Needed because you cannot pass '*password' as a kwarg
    """
    if key == "password":
        return "*password"
    else:
        return key

def field_type(value):
    """Return the type of the field, using the Ref object"""
    if isinstance(value, Ref):
        return "RefValue"
    else:
        return "StringValue"

def field_value(value):
    """REturn the value of the field, using the Ref object"""
    if isinstance(value, Ref):
        return value.ref
    else:
        return value

class DataPipeline(object):
    """Create an AWS Data Pipeline object

    This class is similar to the CloudFormation library, in that
    you create a pipeline object and add elements to the pipeline.
    Elements can reference other elements using the Ref object
    and element name.
    """
    def __init__(self, role="DataPipelineDefaultRole", resource_role="DataPipelineDefaultResourceRole", log_uri=None, fmt="CF"):
        """Create a new DataPipeline object

        Args:
            role (str): IAM role for the Data Pipeline to execute under
            resource_role (str): IAM role for the EC2 instance and EMR cluster
                                 to execute under
            log_uri (uri): S3 URI for the location to store execution logs
            fmt (str): Either 'CF' or 'DP' for the internal format that will
                       be used when adding elements.
                       'CF' for use with CloudFormation templates
                       'DP' for when launching directly in Data Pipeline
        """
        self.fmt = fmt
        self.objects = []

        # Set the schedule for the pipeline
        self.add_field("DefaultSchedule",
                       "DefaultSchedule",
                       type = "Schedule",
                       period = "1 weeks",
                       startAt = "FIRST_ACTIVATION_DATE_TIME")

        # Set default values used by all resources
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
        """Add a new field to the pipeline under construction"""

        def key_(k):
            """Handle the different between CF and DP definitions.
            DP requires some keys to be capitalized while CF requires
            them to be lower case (why did they do this???) """
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
        """Add an EC2 instance to the pipeline

        Args:
            name (str): Name of the resource
            type (str): EC2 Instance type to launch
            sgs ([str]): A List of Security Group Ids to attach to the EC2 instance
            subnet (str): A Subnet Id to launch the EC2 instance into
                          Used to associate the instance with a VPC
            duration (str): A time string (ex '2 Hours') after which the instance
                            will be terminated (if it hasn't finished)
            image (str): AMI image to use when launching the instance
                         NOTE: the image must conform to the Data Pipleline standards
                               or it will not work
        """

        self.add_field(name,
                       name,
                       type = "Ec2Resource",
                       instanceType = type,
                       actionOnTaskFailure = "terminate",
                       securityGroupIds = sgs,
                       subnetId = subnet,
                       imageId = image,
                       terminateAfter = duration)

    def add_emr_cluster(self, name, type="m3.xlarge", count="1", version="3.9.0", region='us-east-1', duration="2 Hours"):
        """Add an Elastic Map Reduce cluster to the pipeline
        (Used for DynamoDB operations)

        Args:
            name (str): Name of the resource
            type (str): EMR reduce instance type to launch (both core and master instances)
            count (str|int): Number of core instances to launch
            version (str): Version string for the EMR AMI to launch
            region (str): AWS Region
            duration (str): A time string (ex '2 Hours') after which the instance
                            will be terminated (if it hasn't finished)
        """

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
        """Add a RDS database definition

        Args:
            name (str): Name of the resource
            instance (str): RDS Instance Id
            username (str): Database username
            password (str): Database password
        """
        self.add_field(name,
                       name,
                       type = "RdsDatabase",
                       jdbcProperties = "allowMultiQueries=true",
                       rdsInstanceId = instance,
                       username = username,
                       password = password)

    def add_rds_table(self, name, database, table):
        """Add a RDS table definition
        Uses a 'SELECT * FROM {table}' to dump the table's data

        Args:
            name (str): Name of the resource
            database (Ref): Reference to the containing database
            table (str): Name of the RDS table
        """
        self.add_field(name,
                       name,
                       type = "SqlDataNode",
                       database = database,
                       table = table,
                       selectQuery = "select * from #{table}")

    def add_ddb_table(self, name, table, read_percent="0.25", write_percent="0.25"):
        """Add a DynamoDB table definition

        Args:
            name (str): Name of the resource
            table (str): Name of the DynamoDB table
            read_percent (str|float): Read Throughput Percentage (ex 0.25)
            write_percent (str|float): Write Throughput Percentage (ex 0.25)
        """
        self.add_field(name,
                       name,
                       type = "DynamoDBDataNode",
                       readThroughputPercent = read_percent,
                       writeThroughputPercent = write_percent,
                       tableName = table)

    def add_s3_bucket(self, name, s3_directory):
        """Add a S3 bucket

        Args:
            name (str): Name of the resource
            s3_directory (uri): S3 URI of the directory to expose
        """
        self.add_field(name,
                       name,
                       type = "S3DataNode",
                       directoryPath = s3_directory)

    def add_rds_copy(self, name, source, destination, runs_on=None):
        """Add a RDS Copy Activity

        Args:
            name (str): Name of the resource
            source (Ref): Source RDS Table
            destination (Ref): S3 data destination
            runs_of (Ref): EC2 instance used to run the copy
        """
        self.add_field(name,
                       name,
                       type = "CopyActivity",
                       input = source,
                       output = destination,
                       runsOn = runs_on)

    def add_emr_copy(self, name, source, destination, runs_on=None, region='us-east-1', export=True):
        """Add a EMR / DynamoDB Copy Activity

        Args:
            name (str): Name of the resource
            source (Ref): DynamoDB table or S3 bucket
            destination (Ref): S3 bucket or DynamoDB table
            runs_on (Ref): EMR cluster to run the copy
            region (str): The AWS region
            export (bool): If the copy is an export or import
        """

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
        """Add a Shell Command

        Args:
            name (str): Name of the resource
            command (str): Shell command to run
            source (Ref): S3 bucket of input data
            destination (Ref): S3 bucket for output data
            runs_on (Ref): EC2 Instance on which to run the command
        """
        self.add_field(name,
                       name,
                       type = "ShellCommandActivity",
                       input = source,
                       output = destination,
                       runsOn = runs_on,
                       stage = "true",
                       command = command)


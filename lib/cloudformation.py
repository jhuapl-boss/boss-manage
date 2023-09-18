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

"""Configuration class and supporting classes for building and launching
Cloudformation templates.

Author:
    Derek Pryor <Derek.Pryor@jhuapl.edu>
"""

import os
import time
import json
from botocore.exceptions import ClientError

from . import hosts
from . import aws
from . import utils
from . import console
from . import lambdas
from . import constants as const
from .migrations import MigrationManager
from .exceptions import BossManageError, BossManageCanceled

def bool_str(val):
    """CloudFormation Template formatted boolean string.

    CloudFormation uses all lowercase for boolean values, which means that
    str() will not work correctly for boolean values.

    Args:
        val (bool) : Boolean value to convert to a string

    Returns:
        (str) : String of representing the boolean value
    """
    return "true" if val else "false"

def Arn(key):
    """Get the Arn attribute of the given template resource"""
    return { 'Fn::GetAtt': [key, 'Arn']}

class Ref(dict):
    """Turn a template key name into a template reference.

    This allows methods to handle both reference and non reference
    values without any work.
    """
    def __init__(self, key):
        super(Ref, self).__init__(self, Ref=key)

    def __str__(self):
        # DP NOTE: by default str / repr formatted python dictionaries
        # are not JSON compatible due to using single quotes
        # Force the format into a JSON compatible format
        return json.dumps(self)

class Arg:
    """Class of static methods to create the CloudFormation template argument
    snippits.
    """

    def __init__(self, key, parameter, value, use_previous=False):
        """Generic constructor used by all of the specific static methods.

        Args:
            key (str) : Unique name associated with the argument
            parameter (dict) : Dictionary of parameter information, as defined
                               by CloudFormation / AWS.
            value (str) : Value of the argument
            use_previous (bool) : Stored under the UsePreviousValue key
        """
        self.key = key
        self.parameter = parameter
        self.argument = {
            "ParameterKey": key,
            "ParameterValue": value,
            "UsePreviousValue": use_previous
        }

    @staticmethod
    def String(key, value, description=""):
        """Create a String argument.

        Args:
            key (str) : Unique name associated with the argument
            value (str) : String value
            description (str) : Argument description, only seen if manually
                                   launching the template
        """
        parameter =  {
            "Description" : description,
            "Type": "String"
        }
        return Arg(key, parameter, value)

    @staticmethod
    def Password(key, value, description=""):
        """Create a String argument that does not show typed characters.

        Args:
            key (str) : Unique name associated with the argument
            value (str) : Password value
            description (str) : Argument description, only seen if manually
                                   launching the template
        """
        parameter =  {
            "Description" : description,
            "Type": "String",
            "NoEcho": "true"
        }
        return Arg(key, parameter, value)

    @staticmethod
    def IP(key, value, description=""):
        """Create a String argument that checks the value to make sure it is in
        a valid IPv4 format.

        Note: Valid IPv4 format is x.x.x.x through xxx.xxx.xxx.xxx, the actual
              subnet number is not checked to make sure it is between 0 and 255

        Args:
            key (str) : Unique name associated with the argument
            value (str) : IPv4 value
            description (str) : Argument description, only seen if manually
                                   launching the template
        """
        parameter = {
            "Description" : description,
            "Type": "String",
            "MinLength": "7",
            "MaxLength": "15",
            "Default": "0.0.0.0",
            "AllowedPattern": "(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})",
            "ConstraintDescription": "must be a valid IP of the form x.x.x.x."
        }
        return Arg(key, parameter, value)

    @staticmethod
    def Port(key, value, description=""):
        """Create a Number argument that checks the value to make sure it is a
        valid port number.

        Args:
            key (str) : Unique name associated with the argument
            value (string|int) : Port value
            description (str) : Argument description, only seen if manually
                                   launching the template
        """
        parameter =  {
            "Description" : description,
            "Type": "Number",
            "MinValue": "1",
            "MaxValue": "65535"
        }
        return Arg(key, parameter, value)

    @staticmethod
    def CIDR(key, value, description=""):
        """Create a String argument that checks the value to make sure it is in
        a valid IPv4 CIDR format.

        Note: Valid IPv4 CIDR format is x.x.x.x/x through xxx.xxx.xxx.xxx/xx, the
              actual subnet number is not checked to make sure it is between 0
              and 255 and the CIDR mask is not checked to make sure its is between
              1 and 32

        Args:
            key (str) : Unique name associated with the argument
            value (str) : IPv4 CIDR value
            description (str) : Argument description, only seen if manually
                                   launching the template
        """
        parameter = {
            "Description" : description,
            "Type": "String",
            "MinLength": "9",
            "MaxLength": "18",
            "Default": "0.0.0.0/0",
            "AllowedPattern": "(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})\\.(\\d{1,3})/(\\d{1,2})",
            "ConstraintDescription": "must be a valid IP CIDR range of the form x.x.x.x/x."
        }
        return Arg(key, parameter, value)

    @staticmethod
    def VPC(key, value, description=""):
        """Create a VPC ID argument that makes sure the value is a valid VPC ID.

        Args:
            key (str) : Unique name associated with the argument
            value (str) : VPC ID value
            description (str) : Argument description, only seen if manually
                                   launching the template
        """
        parameter = {
            "Description" : description,
            "Type": "AWS::EC2::VPC::Id"
        }
        return Arg(key, parameter, value)

    @staticmethod
    def Subnet(key, value, description=""):
        """Create an (AWS) Subnet ID argument that makes sure the value is a
        valid Subnet ID.

        Args:
            key (str) : Unique name associated with the argument
            value (str) : Subnet ID value
            description (str) : Argument description, only seen if manually
                                   launching the template
        """
        parameter = {
            "Description" : description,
            "Type": "AWS::EC2::Subnet::Id"
        }
        return Arg(key, parameter, value)

    @staticmethod
    def AMI(key, value, description=""):
        """Create a AMI ID argument that makes sure the value is a valid AMI ID.

        Args:
            key (str) : Unique name associated with the argument
            value (str) : AMI ID value
            description (str) : Argument description, only seen if manually
                                   launching the template
        """
        parameter = {
            "Description" : description,
            "Type": "AWS::EC2::Image::Id"
        }
        return Arg(key, parameter, value)

    @staticmethod
    def Instance(key, value, description=""):
        """Create a Instance ID argument that makes sure the value is a valid Instance ID.

        Args:
            key (str) : Unique name associated with the argument
            value (str) : Instance ID value
            description (str) : Argument description, only seen if manually
                                   launching the template
        """
        parameter = {
            "Description" : description,
            "Type": "AWS::EC2::Instance::Id"
        }
        return Arg(key, parameter, value)

    @staticmethod
    def KeyPair(key, value, hostname):
        """Create a KeyPair KeyName argument that makes sure the value is a
        valid KeyPair name.

        Args:
            key (str) : Unique name associated with the argument
            value (str) : Key Pair value
            description (str) : Argument description, only seen if manually
                                   launching the template
        """
        parameter = {
            "Description" : "Name of an existing EC2 KeyPair to enable SSH access to '{}'".format(hostname),
            "Type": "AWS::EC2::KeyPair::KeyName",
            "ConstraintDescription" : "must be the name of an existing EC2 KeyPair."
        }
        return Arg(key, parameter, value)

    @staticmethod
    def SecurityGroup(key, value, description=""):
        """Create a SecurityGroup ID argument that makes sure the value is a
        valid SecurityGroup ID.

        Args:
            key (str) : Unique name associated with the argument
            value (str) : Security Group ID value
            description (str) : Argument description, only seen if manually
                                   launching the template
        """
        parameter = {
            "Description" : description,
            "Type": "AWS::EC2::SecurityGroup::Id"
        }
        return Arg(key, parameter, value)

    @staticmethod
    def RouteTable(key, value, description=""):
        """Create a RouteTable ID argument.

        NOTE: AWS does not currently recognize AWS::EC2::RouteTable::Id as a
              valid argument type. Therefore this argument is a String
              argument.

        Args:
            key (str) : Unique name associated with the argument
            value (str) : Route Table ID value
            description (str) : Argument description, only seen if manually
                                   launching the template
        """
        parameter = {
            "Description" : description,
            "Type" : "For whatever reason CloudFormation does not recognize RouteTable::Id",
            "Type" : "AWS::EC2::RouteTable::Id",
            "Type" : "String"
        }
        return Arg(key, parameter, value)

    @staticmethod
    def Certificate(key, value, description=""):
        """Create a Certificate ID argument that makes sure the value is a
        valid Certificate ID.

        Args:
            key (str) : Unique name associated with the argument
            value (str) : Certificate ID value
            description (str) : Argument description, only seen if manually
                                   launching the template
        """
        parameter = {
            "Description" : description,
            "Type": "AWS::ACM::Certificate::Id"
        }
        return Arg(key, parameter, value)

# Developer Note
#
# Template arguments vs Hardcoded values
#
# One of the time that you should use a template argument over a hardcoded value is
# when the value is the result of a AWS lookup. The reason for this is if the code
# is being use to offline generate a template file, the AWS lookup result will be
# None, which is not a valid template value.
#
# The other time is when the value is (could be) a reference to another resource
# either in the same template or already created in AWS.
#
# In most cases using a template argument will also enforce a check to make sure
# it is a valid value.
#
# In all other cases, it is up to the developer of new methods to decide if they
# want to implement the function's arguments are CF template arguments or hardcoded
# values.
class CloudFormationConfiguration:
    """Configuration class that helps with building CloudFormation templates
    and launching them.
    """

    def __init__(self, config, bosslet_config, version="1"):
        """CloudFormationConfiguration constructor

        A domain name is in either <vpc>.<tld> or <subnet>.<vpc>.<tld> format and
        is validated by hosts.py to determine the IP subnets.

        Note: region is used when creating the Hosted Zone for a new VPC.

        Args:
            config (str) : Name of the configuration being constructed
            domain (str) : Domain that the CloudFormation template will work in.
            region (optional[str]) : AWS region that the configuration will be created in.
            version (optional[str]) : Version number for the configuration, used for update migration
        """
        self.resources = {}
        self.parameters = {}
        self.outputs = None
        self.capabilities = None
        self.arguments = []
        self.region = bosslet_config.REGION
        self.keypairs = {}

        self.config = config
        self.stack_name = bosslet_config.names[config].stack
        self.stack_version = version

        self.bosslet_config = bosslet_config
        self.session = bosslet_config.session
        self.hosts = hosts.Hosts(bosslet_config)

        self.vpc_domain = bosslet_config.INTERNAL_DOMAIN
        self.vpc_subnet = bosslet_config.NETWORK


    def _create_template(self, description="", indent=None):
        """Create the JSON CloudFormation template from the resources that have
        be added to the object.

        Args:
            description (str) : Template description

        Returns:
            (str) : The JSON formatted CloudFormation template
        """
        template = {
            "AWSTemplateFormatVersion" : "2010-09-09",
            "Description" : description,
            "Parameters": self.parameters,
            "Resources": self.resources
        }

        if self.outputs is not None:
            template["Outputs"] = self.outputs

        return json.dumps(template, indent=indent)

    def version(self):
        """Get the version of this CloudFormationConfiguration object"""
        return int(self.stack_version)

    def existing_version(self):
        """Get the version of this CloudFormationConfiguration stack running in AWS

        Note: If the CloudFormation Stack was created before they were versioned the
              default version (1) will be returned

        Returns:
            (int|None) : The version of the running stack or None if the stack is not running
        """
        client = self.session.client('cloudformation')

        try:
            response = client.describe_stacks(StackName = self.stack_name)
            tags = response['Stacks'][0]['Tags']
            for tag in tags:
                if tag['Key'] == 'StackVersion':
                    return int(tag['Value'])
            return 1 # Default value for Stacks that are not already versioned
        except ClientError:
            return None # Stack doesn't exist

    def generate(self):
        """Generate the CloudFormation template and arguments files """
        cur_dir = os.path.dirname(os.path.realpath(__file__))
        folder = os.path.realpath(os.path.join(cur_dir, '..', 'cloud_formation', 'templates'))

        with open(os.path.join(folder, self.stack_name + ".template"), "w") as fh:
            fh.write(self._create_template(indent=4))

        with open(os.path.join(folder, self.stack_name + ".arguments"), "w") as fh:
            json.dump(self.arguments, fh, indent=4)

    def _poll(self, client, name, action, process):
        get_status = lambda r: r['Stacks'][0]['StackStatus']
        response = client.describe_stacks(StackName=name)
        if len(response['Stacks']) == 0:
            msg = "Stack '{}' doesn't exist".format(name)
            raise BossManageError(msg)
        else:
            print("Waiting for {} ".format(action), end="", flush=True)
            while get_status(response) == process:
                time.sleep(5)
                print(".", end="", flush=True)
                response = client.describe_stacks(StackName=name)
            print(" done")

            return get_status(response)

    def _raise_error(self, status):
        """A common method for raising an error if create/update/delete didn't
        result in the expected status. If the status if FAILED then the failures
        are included in the exception.
        """
        msg = "Status of stack '{}' is '{}'".format(self.stack_name, status)
        causes = None

        if 'FAILED' in status or 'ROLLBACK' in status:
            causes = self.get_failed_reasons()

        raise BossManageError(msg, causes=causes)

    def create(self, wait = True):
        """Launch the template this object represents in CloudFormation.

        Args:
            session (Session) : Boto3 session used to launch the configuration
            wait (bool) : If True, wait for the stack to be created, printing
                          status information

        Raises:
            BossManageError: If there was a problem creating the stack
        """
        for argument in self.arguments:
            arg_val = argument['ParameterValue']
            if arg_val is None:
                msg = "Could not determine argument '{}'".format(arg_val)
                raise BossManageError(msg)

        client = self.session.client('cloudformation')

        kwargs = {
            "StackName": self.stack_name,
            "TemplateBody": self._create_template(),
            "Parameters": self.arguments,
            "Tags": [
                {"Key": "StackVersion", "Value": self.stack_version},
                {"Key": "Commit", "Value": utils.get_commit()}
            ]
        }

        if self.capabilities is not None:
            kwargs['Capabilities'] = self.capabilities 

        try:
            response = client.create_stack(**kwargs)
        except client.exceptions.AlreadyExistsException:
            msg = "Stack '{}' already exists".format(self.stack_name)
            raise BossManageError(msg)

        if wait:
            status = self._poll(client, self.stack_name, 'create', 'CREATE_IN_PROGRESS')

            if status == 'CREATE_COMPLETE':
                print("Created stack '{}'".format(self.stack_name))
            else:
                self._raise_error(status)

    def update(self, wait = True):
        """Update the template this object represents in CloudFormation.

        Args:
            session (Session) : Boto3 session used to launch the configuration
            wait (bool) : If True, wait for the stack to be updated, printing
                          status information

        Returns:
            bool: If there were migrations applied

        Raises:
            BossManageCanceled: If the update was canceled
            BossManageError: If there was a problem updating the stack
        """
        for argument in self.arguments:
            arg_val = argument['ParameterValue']
            if arg_val is None:
                msg = "Could not determine argument '{}'".format(arg_val)
                raise BossManageError(msg)

        client = self.session.client('cloudformation')
        migrations = MigrationManager(self.config, self.existing_version(), self.version())

        # Save the migration progress in case there is an exception in one
        # The "update-migration" command will allow the user to continue executing
        # migrations from where they failed
        migration_progress = const.repo_path('cloud_formation', 'configs', 'migrations', self.config, 'progress')
        with open(migration_progress, 'w') as fh:
            fh.write(str(migrations.cur_ver))

        def update_stack_version(self, migration_file):
            with open(migration_progress, 'w') as fh:
                fh.write(str(migration_file.stop))
        migrations.add_callback(post = update_stack_version)

        kwargs = {
            "StackName": self.stack_name,
            "TemplateBody": self._create_template(),
            "Parameters": self.arguments,
            "Tags": [
                {"Key": "StackVersion", "Value": self.stack_version},
                {"Key": "Commit", "Value": utils.get_commit()}
            ]
        }

        if self.capabilities is not None:
            kwargs['Capabilities'] = self.capabilities 

        disable_preview = str(self.bosslet_config.disable_preview)
        disable_preview = disable_preview.lower() in ('yes', 'true', 'y', 't')
        if disable_preview:
            migrations.pre_update(self.bosslet_config)
            response = client.update_stack(**kwargs)
        else:
            commit = utils.get_commit()
            kwargs['ChangeSetName'] = 'h' + commit
            response = client.create_change_set(**kwargs)

            try:
                response = {'Status': 'CREATE_PENDING'}
                while response['Status'] in ('CREATE_PENDING', 'CREATE_IN_PROGRESS'):
                    time.sleep(5)
                    response = client.describe_change_set(
                        ChangeSetName = 'h' + commit,
                        StackName = self.stack_name
                    )

                if response['Status'] != 'CREATE_COMPLETE':
                    if "didn't contain changes" in response['StatusReason']:
                        console.info("No changes detected, nothing to update")
                        return

                    print("ChangeSet status is {}".format(response['Status']))
                    raise BossManageError(response['StatusReason'])

                fmt = "{:<10}{:<30}{:<50}{:<45}{:<14}{}"
                print(fmt.format(
                    "Action",
                    "Logical ID",
                    "Physical ID",
                    "Resource Type",
                    "Replacement",
                    "Scope"
                ))
                for change in response['Changes']:
                    if change['Type'] == 'Resource':
                        change = change['ResourceChange']
                        limit = lambda s: s[:42] + "..." if len(s) > 45 else s
                        print(fmt.format(
                            change['Action'],
                            change['LogicalResourceId'],
                            limit(change.get('PhysicalResourceId', '')),
                            change['ResourceType'],
                            change.get('Replacement', ''),
                            ", ".join(change['Scope'])
                        ))

                if not console.confirm('Apply Update?', default = False):
                    raise BossManageCanceled()
                else:
                    migrations.pre_update(self.bosslet_config)
                    response = client.execute_change_set(
                        ChangeSetName = 'h' + commit,
                        StackName = self.stack_name
                    )
            except:
                client.delete_change_set(
                    ChangeSetName = 'h' + commit,
                    StackName = self.stack_name
                )
                raise

        if wait:
            status = self._poll(client, self.stack_name, 'update', 'UPDATE_IN_PROGRESS')

            if status == 'UPDATE_COMPLETE':
                print("Updated stack '{}'".format(self.stack_name))
            elif status == 'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS':
                status = self._poll(client, self.stack_name, 'update cleanup', 'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS')
                print("Updated stack '{}'".format(self.stack_name))
            else:
                self._raise_error(status)

        migrations.post_update(self.bosslet_config)

        os.remove(migration_progress)

        return migrations.has_migrations

    def delete(self, wait = True):
        """Deletes the given stack from CloudFormation.

        Initiates the stack delete and waits for it to finish.  config and domain
        are combined to identify the stack.

        Args:
            session (boto3.Session): An active session.
            domain (str): Name of domain.
            wait (bool) : If True, wait for the stack to be deleted, printing
                          status information

        Raises:
            BossManageError: If there was a problem deleting the stack
        """

        client = self.session.client("cloudformation")
        client.delete_stack(StackName = self.stack_name)

        if wait:
            try:
                status = self._poll(client, self.stack_name, 'delete', 'DELETE_IN_PROGRESS')

                if status == 'DELETE_COMPLETE':
                    print("Deleted stack '{}'".format(self.stack_name))
                else:
                    self._raise_error(status)
            except ClientError:
                # Stack doesn't exist anymore
                print(" done")

    def get_failed_reasons(self):
        client = self.session.client("cloudformation")

        events = []
        args = {'StackName': self.stack_name}
        while 'NextToken' not in args or args['NextToken'] is not None:
            resp = client.describe_stack_events(**args)

            events.extend(['{}: {}'.format(e['LogicalResourceId'], e['ResourceStatusReason'])
                           for e in resp['StackEvents']
                           if e['ResourceStatus'].endswith('_FAILED')])

            if 'NextToken' in resp:
                args['NextToken'] = resp['NextToken']
            else:
                args['NextToken'] = None

        return events

    def add_arg(self, arg):
        """Add an Arg class instance to the internal configuration.

        Args:
            arg (Arg) : Arg instance to add to the template
        """
        if arg.key not in self.parameters:
            self.parameters[arg.key] = arg.parameter
            self.arguments.append(arg.argument)

    def add_output(self, logical_id, value, export_name, desc):
        """Add an output so the resource may be imported by another CloudFormation template.

        Args:
            logical_id (str): Name used in template.
            value (dict|str): Value returned by output.  Pass a dict if using a CloudFormation intrinsic function.
            export_name (str): Name other templates use to import output.
            desc (str): Output description.
        """
        if self.outputs is None:
            self.outputs = {}

        self.outputs[logical_id] = {
            "Description": desc,
            "Value": value,
            "Export": { "Name": export_name },
        }

    def add_capabilities(self, caps):
        """Add capabilities to the configuration.

        Add this if a InsufficentCapabilitiesException is raised.

        Args:
            caps (list[str]): 'CAPABILITY_IAM | 'CAPABILITY_NAMED_IAM'
        """
        self.capabilities = caps

    def add_vpc(self, key="VPC"):
        """Add a VPC to the configuration.

        VPC name is derived from the domain given to the constructor.

        Args:
            key (str) : Unique name for the resource in the template
        """
        self.resources[key] = {
            "Type" : "AWS::EC2::VPC",
            "Properties" : {
                "CidrBlock" : self.vpc_subnet,
                "EnableDnsSupport" : "true",
                "EnableDnsHostnames" : "true",
                "Tags" : [
                    {"Key" : "Stack", "Value" : Ref("AWS::StackName") },
                    {"Key" : "Name", "Value" : self.vpc_domain }
                ]
            }
        }

        self.resources["DNSZone"] = {
            "Type" : "AWS::Route53::HostedZone",
            "Properties" : {
                "HostedZoneConfig" : {
                    "Comment": "Internal DNS Zone for the VPC of {}".format(self.vpc_domain)
                },
                "Name" : self.vpc_domain,
                "VPCs" : [ {
                    "VPCId": Ref(key),
                    "VPCRegion": self.region
                }]
            }
        }

    def find_vpc(self, key="VPC"):
        """Lookup a VPC's ID and add it to the configuration as an argument

        VPC name is derived fromt he domain given to the constructor

        Args:
            session (Session) : Boto3 session used to lookup the VPC's ID
            key (str) : Unique name for the resource in the template
        """

        vpc_id = aws.vpc_id_lookup(self.session, self.vpc_domain)
        vpc = Arg.VPC(key, vpc_id, "ID of the VPC")
        self.add_arg(vpc)
        return vpc_id

    def add_subnet(self, key, name, vpc=Ref("VPC"), az=None):
        """Add a Subnet to the configuration.

        Subnet name is derived from the domain given to the constructor.

        Args:
            key (str) : Unique name for the resource in the template
            name (str) : Name of the subnet being added
            vpc (str) : VPC ID or Ref for the VPC the subnet will be created in
            az (string|None) : Availability Zone to launch the subnet in or None
                               to allow AWS to decide
        """

        self.resources[key] = {
            "Type" : "AWS::EC2::Subnet",
            "Properties" : {
                "VpcId" : vpc,
                "CidrBlock" : self.hosts.lookup(name),
                "Tags" : [
                    {"Key" : "Stack", "Value" : Ref("AWS::StackName") },
                    {"Key" : "Name", "Value" : name }
                ]
            }
        }

        if az is not None:
            self.resources[key]["Properties"]["AvailabilityZone"] = az

    def add_all_subnets(self):
        """Add Internal and External subnets for each availability zone.

        For each availability zone in the connected region, create an Internal
        and External subnets so that AWS resources like AutoScale Groups can
        run across all zones within the region.

        Args:

        Returns:
            (tuple) : Tuple of two lists (internal, external) that contain the
                      template argument names for each of the added subnets
        """
        internal = []
        external = []
        for az, sub in aws.azs_lookup(self.bosslet_config):
            name = sub.capitalize() + "InternalSubnet"
            self.add_subnet(name, sub + "-internal." + self.vpc_domain, az = az)
            internal.append(Ref(name))

            name = sub.capitalize() + "ExternalSubnet"
            self.add_subnet(name, sub + "-external." + self.vpc_domain, az = az)
            external.append(Ref(name))

        return (internal, external)

    def add_all_lambda_subnets(self):
        """Add Lambda specific internal subnets.

        Needed as the large number of Lambda executions can quickly use up all
        of the IP address in the regular internal subnets.

        For each lambda subnet allocated in lib.hosts create a subnet, distributed
        evenly over the lambda compatible availability zones

        Args:

        Returns:
            (list) : List of template references for each of the added subnets
        """
        internal = []

        # transforms [(AZ_Name, AZ_Letter)] -> ([AZ_Name], [AZ_Letter])
        azs = list(zip(*aws.azs_lookup(self.bosslet_config, compatibility='lambda')))[0]
        print("Lambda AZs: {}".format(azs))
        subnets = [x for x in hosts.SUBNETS if x.startswith('lambda')]

        for i in range(len(subnets)):
            key = "LambdaSubnet{}".format(i)
            self.add_subnet(key, subnets[i] + "." + self.vpc_domain, az = azs[i % len(azs)])
            internal.append(Ref(key))

        return internal


    def find_all_subnets(self, compatibility=None):
        """Add template arguments for each internal/external availability zone subnet.

        A companion method to add_all_subnets(), that will either add a reference to
        the subnets currently in the configuration or lookup the subnet ids and add an
        argument for each subnet that exists in the current region.

        Args:
            compatibility (str|None): Availibility Zone usage down selection
        Returns:
            (tuple) : Tuple of two lists (internal, external) that contain the
                      template argument names for each of the added subnet arguments
        """
        internal = []
        external = []

        for az, sub in aws.azs_lookup(self.bosslet_config, compatibility):
            name = sub.capitalize() + "InternalSubnet"
            if name in self.resources:
                internal.append(Ref(name))
            else:
                domain = sub + "-internal." + self.vpc_domain
                id = aws.subnet_id_lookup(self.session, domain)
                if id is None:
                    print("Subnet {} doesn't exist, not using.".format(domain))
                else:
                    self.add_arg(Arg.Subnet(name, id))
                    internal.append(Ref(name))

            name = sub.capitalize() + "ExternalSubnet"
            if name in self.resources:
                external.append(Ref(name))
            else:
                domain = sub + "-external." + self.vpc_domain
                id = aws.subnet_id_lookup(self.session, domain)
                if id is None:
                    print("Subnet {} doesn't exist, not using.".format(domain))
                else:
                    self.add_arg(Arg.Subnet(name, id))
                    external.append(Ref(name))

        return (internal, external)

    def find_all_lambda_subnets(self):
        """Add template arguments for each internal lambda subnet.

        A companion method to add_all_lambda_subnets(), that will either add a reference
        to the subnets currently in the configuration or lookup the subnet ids and add an
        argument for each subnet that exists in the current region.

        Args:
            compatibility (str|None): Availibility Zone usage down selection
        Returns:
            (tuple) : Tuple of two lists (internal, external) that contain the
                      template argument names for each of the added subnet arguments
        """
        internal = []

        subnets = [x for x in hosts.SUBNETS if x.startswith('lambda')]

        for i in range(len(subnets)):
            key = "LambdaSubnet{}".format(i)
            if key in self.resources:
                internal.append(Ref(key))
            else:
                domain = subnets[i] + "." + self.vpc_domain
                id = aws.subnet_id_lookup(self.session, domain)
                if id is None:
                    print("Subnet {} doesn't exist, not using.".format(domain))
                else:
                    self.add_arg(Arg.Subnet(key, id))
                    internal.append(Ref(key))

        return internal

    def add_endpoint(self, key, service, route_tables, vpc="VPC"):
        self.resources[key] = {
            "Type" : "AWS::EC2::VPCEndpoint",
            "Properties" : {
                #"PolicyDocument" : JSON object, # allow full access
                "RouteTableIds" : route_tables,
                "ServiceName" : 'com.amazonaws.{}.{}'.format(self.region, service),
                "VpcId" : {"Ref": vpc},
            }
        }

    def add_nat(self, key, subnet, depends_on=None):
        self.resources[key] = {
            "Type" : "AWS::EC2::NatGateway",
            "Properties" : {
                "AllocationId" : { 'Fn::GetAtt': [key + "IP", "AllocationId"]},
                "SubnetId" : subnet,
            }
        }

        if depends_on is not None:
            self.resources[key]["DependsOn"] = depends_on

        self.resources[key + "IP"] = {
            "Type" : "AWS::EC2::EIP",
            "Properties" : {
                "Domain" : "vpc"
            }
        }

    def add_ec2_instance(self, key, hostname, ami, keypair, subnet=Ref("Subnet"), type_="t2.micro", iface_check=True, public_ip=False, security_groups=None, user_data=None, meta_data=None, role=None, depends_on=None):
        """Add an EC2 instance to the configuration

        Args:
            key (str) : Unique name for the resource in the template
            hostname (str) : The hostname / instance name of the instance
            ami (str) : The AMI ID of the image to base the instance on
            subnet (string|Ref) : The Subnet ID or Ref of the Subnet to launch this machine in
            type_ (str) : The instance type to create
            iface_check (bool) : Should the network check if the traffic is destined for itself
                                 (usedful for NAT instances)
            public_ip (bool) : Should the instance gets a public IP address
            security_groups (None|list) : A list of SecurityGroup IDs or Refs
            user_data (None|string) : A string of user-data to give to the instance when launching
            meta_data (None|dict) : A dictionary of meta-data to include with the configuration
            role (None|string) : The role name of that the ec2 instance can assume.
            depends_on (None|string|list): A unique name or list of unique names of resources within the
                                           configuration and is used to determine the launch order of resources
        """

        commit = None
        if type(ami) == tuple:
            commit = ami[1]
            ami = ami[0]

        self.resources[key] = {
            "Type" : "AWS::EC2::Instance",
            "Properties" : {
                "ImageId" : ami,
                "InstanceType" : type_,
                "KeyName" : keypair,
                "SourceDestCheck": bool_str(iface_check),
                "Tags" : [
                    {"Key" : "Stack", "Value" : Ref("AWS::StackName") },
                    {"Key" : "Name", "Value" : hostname }
                ],
                "NetworkInterfaces" : [{
                    "AssociatePublicIpAddress" : bool_str(public_ip),
                    "DeviceIndex"              : "0",
                    "DeleteOnTermination"      : "true",
                    "SubnetId"                 : subnet,
                }]
            }
        }

        if commit is not None:
            kv = {"Key": "AMI Commit", "Value": commit}
            self.resources[key]["Properties"]["Tags"].append(kv)

        if depends_on is not None:
            self.resources[key]["DependsOn"] = depends_on

        if security_groups is not None:
            self.resources[key]["Properties"]["NetworkInterfaces"][0]["GroupSet"] = security_groups

        if meta_data is not None:
            self.resources[key]["Metadata"] = meta_data

        if user_data is not None:
            self.resources[key]["Properties"]["UserData"] = { "Fn::Base64" : user_data }

        if role is not None:
            self.resources[key]["Properties"]["IamInstanceProfile"] = role


        self.keypairs[hostname] = keypair
        self._add_record_cname(key, hostname, ec2 = True)

    def add_rds_db(self, key, hostname, port, db_name, username, password, subnets, type_="db.t2.micro", storage="5", security_groups=None):
        """Add an RDS DB instance to the configuration

        Args:
            key (str) : Unique name for the resource in the template
            hostname (str) : The hostname / instance name of the RDS DB
            port (int) : The port for the DB instance to listen on
            db_name (str) : The name of the database to create on the DB instance
            username (str) : The master username for the database
            password (str) : The (plaintext) password for the master username
            subnets (list) : A list of Subnet IDs or Refs across which
                             to create a DB SubnetGroup for the DB Instance to launch into
            type_ (str) : The RDS instance type to create
            storage (int|string) : The storage size of the database (in GB)
            security_groups (None|list) : A list of SecurityGroup IDs or Refs
        """
        hostname_ = hostname.replace('.','-')

        self.resources[key] = {
            "Type" : "AWS::RDS::DBInstance",

            "Properties" : {
                "Engine" : "mysql",
                "LicenseModel" : "general-public-license",
                "EngineVersion" : "5.7.39",  # was 5.6.48
                "DBInstanceClass" : type_,
                "MultiAZ" : "true",
                "StorageType" : "standard",
                "AllocatedStorage" : str(storage),
                "DBInstanceIdentifier" : hostname_,
                "MasterUsername" : username,
                "MasterUserPassword" : password,
                "DBSubnetGroupName" : Ref(key + "SubnetGroup"),
                "PubliclyAccessible" : "false",
                "DBName" : db_name,
                "Port" : port,
                "StorageEncrypted" : "false"
            },

            "DeletionPolicy": "Delete" # By default CF creates a snapshot
        }

        self.resources[key + "SubnetGroup"] = {
            "Type" : "AWS::RDS::DBSubnetGroup",
            "Properties" : {
                "DBSubnetGroupDescription" : hostname_,
                "SubnetIds" : subnets
            }
        }

        if security_groups is not None:
            self.resources[key]["Properties"]["VPCSecurityGroups"] = security_groups

        self._add_record_cname(key, hostname, rds = True)

    def add_dynamo_table_from_json(self, key, name, KeySchema, AttributeDefinitions, ProvisionedThroughput=None, GlobalSecondaryIndexes=None, TimeToLiveSpecification=None, BillingMode=None):
        """Add DynamoDB table to the configuration using DynamoDB's calling convention.

        Example:
            dynamoschema.json should look like
            {
                'KeySchema' : [{'AttributeName': 'thename', 'KeyType': 'thetype'}],
                'AttributeDefinitions' : [{'AttributeName': 'thename', 'AttributeType': 'thetype'}],
                'ProvisionedThroughput' : {'ReadCapacityUnits': 10, 'WriteCapacityUnits': 10}
            }

            with open('dynamoschema.json', 'r') as jsoncfg:
                tablecfg = json.load(jsoncfg)
                config.add_dynamo_table_from_json('thekey', 'thename', **tablecfg)

        Args:
            key (str) : Unique name (within the configuration) for this instance
            name (str) : DynamoDB Table name to create
            KeySchema (list) : List of dict of AttributeName / KeyType
            AttributeDefinitions (list) : List of dict of AttributeName / AttributeType
            ProvisionedThroughput (optional[dict]) : Dictionary of ReadCapacityUnits / WriteCapacityUnits
            GlobalSecondaryIndexes (optional[list]): List of dicts representing global secondary indexes.  Defaults to None.
            TimeToLiveSpecification (optional[dict]): Defines TTL attribute and whether it's enabled.
            BillingMode (optional[str]): Define billing mode for table.
        """

        self.resources[key] = {
            "Type" : "AWS::DynamoDB::Table",
            "Properties" : {
                "TableName" : name,
                "KeySchema" : KeySchema,
                "AttributeDefinitions" : AttributeDefinitions,
            }
        }

        if ProvisionedThroughput is not None:
            self.resources[key]["Properties"]["ProvisionedThroughput"] = ProvisionedThroughput

        if GlobalSecondaryIndexes is not None:
            self.resources[key]["Properties"]["GlobalSecondaryIndexes"] = GlobalSecondaryIndexes

        if TimeToLiveSpecification is not None:
            self.resources[key]["Properties"]["TimeToLiveSpecification"] = TimeToLiveSpecification

        if BillingMode is not None:
            self.resources[key]["Properties"]["BillingMode"] = BillingMode

    def add_dynamo_table(self, key, name, attributes, key_schema, throughput=None, ondemand=False):
        """Add an DynamoDB Table to the configuration

        Note that either throughput or ondemand must be provided, but not both.

        Args:
            key (str) : Unique name (within the configuration) for this instance
            name (str) : DynamoDB Table name to create
            attributes (list[tuple]) : List of tuples containing [('AttributeName', 'AttributeType'), ...]
            key_schema (list[tuple]) : List of tuples containing [('AttributeName', 'KeyType'), ...]
            throughput (tuple) : Tuple of (ReadCapacity, WriteCapacity).  Defaults to None.
                                 ReadCapacity is the minimum number of consistent reads of items per second
                                              before Amazon DynamoDB balances the loads
                                 WriteCapacity is the minimum number of consistent writes of items per second
                                               before Amazon DynamoDB balances the loads
            ondemand (boolean) : Defaults to False.  Use ondemand provisioning

        Raises:
            (BossManageError): If throughput is not None and ondemand == True or if neither specified.
        """
        if throughput is not None and ondemand:
            raise BossManageError('Cannot specify throughput and ondemand')

        attr_defs = []
        for key_, attr in attributes:
            attr_defs.append({"AttributeName": key_, "AttributeType": attr})

        key_schema_ = []
        for key_, schema in key_schema:
            key_schema_.append({"AttributeName": key_, "KeyType": schema})

        self.resources[key] = {
            "Type" : "AWS::DynamoDB::Table",
            "Properties" : {
                "TableName" : name,
                "AttributeDefinitions" : attr_defs,
                "KeySchema" : key_schema_
            }
        }

        if throughput is not None:
            self.resources[key]['Properties']['ProvisionedThroughput'] = {
                "ReadCapacityUnits" : int(throughput[0]),
                "WriteCapacityUnits" : int(throughput[1])
            }
        elif ondemand:
            self.resources[key]['Properties']['BillingMode'] = 'PAY_PER_REQUEST'
        else:
            raise BossManageError('Must either specify throughput or ondemand=True')

    def add_redis_cluster(self, key, hostname, subnets, security_groups, type_="cache.t2.micro", port=6379, version="2.8.24"):
        """Add a Redis ElastiCache cluster to the configuration

            Note: Redis ElastiCache clusters are limited to 1 node. For a multi- node
                  cluster using ElastiCache use the add_redis_replication() method.

        Args:
            key (str) : Unique name for the resource in the template
            hostname (str) : The hostname / instance name of the Redis Cache
            subnets (list) : A list of Subnet IDs or Refs across which to create a ElastiCache
                             SubnetGroup for the ElastiCache Instance to launch into
            security_groups (list) : A list of SecurityGroup IDs or Refs
            type_ (str) : The ElastiCache instance type to create
            port (int) : The port for the Redis instance to listen on
            version (str) : Redis version to run on the instance
        """
        self.resources[key] =  {
            "Type" : "AWS::ElastiCache::CacheCluster",
            "Properties" : {
                #"AutoMinorVersionUpgrade" : "false", # defaults to true - Indicates that minor engine upgrades will be applied automatically to the cache cluster during the maintenance window.
                "CacheNodeType" : type_,
                "CacheSubnetGroupName" : Ref(key + "SubnetGroup"),
                "Engine" : "redis",
                "EngineVersion" : version,
                "NumCacheNodes" : "1",
                "Port" : port,
                #"PreferredMaintenanceWindow" : String, # don't know the default - site says minimum 60 minutes, infrequent and announced on AWS forum 2w prior
                "Tags" : [
                    {"Key" : "Stack", "Value" : Ref("AWS::StackName") },
                    {"Key" : "Name", "Value" : hostname }
                ],
                "VpcSecurityGroupIds" :  security_groups
            },
            "DependsOn" : key + "SubnetGroup"
        }

        self.resources[key + "SubnetGroup"] = {
            "Type" : "AWS::ElastiCache::SubnetGroup",
            "Properties" : {
                "Description" : hostname,
                "SubnetIds" : subnets
            }
        }

        self._add_record_cname(key, hostname, cluster = True)

    def add_redis_replication(self, key, hostname, subnets, security_groups, type_="cache.m3.medium", port=6379, version="6.2", clusters=1, parameters={}):
        """Add a Redis ElastiCache Replication Group to the configuration

        Args:
            key (str) : Unique name for the resource in the template
            hostname (str) : The hostname / instance name of the Redis Cache
            subnets (list) : A list of Subnet IDs or Refs across which to create a ElastiCache
                             SubnetGroup for the ElastiCache Instance to launch into
            security_groups (list) : A list of SecurityGroup IDs or Refs
            type_ (str) : The ElastiCache instance type to create
            port (int|string) : The port for the Redis instance to listen on
            version (str) : Redis version to run on the instance
            clusters (int|string) : Number of cluster instances to create (1 - 5)
            parameters (dict): Key/Values of Redis configuration parameters
        """
        clusters = int(clusters)
        self.resources[key] =  {
            "Type" : "AWS::ElastiCache::ReplicationGroup",
            "Properties" : {
                "AutomaticFailoverEnabled" : bool_str(clusters > 1),
                #"AutoMinorVersionUpgrade" : "false", # defaults to true - Indicates that minor engine upgrades will be applied automatically to the cache cluster during the maintenance window.
                "CacheNodeType" : type_,
                "CacheSubnetGroupName" : Ref(key + "SubnetGroup"),
                "Engine" : "redis",
                "EngineVersion" : version,
                "NumCacheClusters" : clusters,
                "Port" : int(port),
                #"PreferredCacheClusterAZs" : [ String, ... ],
                #"PreferredMaintenanceWindow" : String, # don't know the default - site says minimum 60 minutes, infrequent and announced on AWS forum 2w prior
                "ReplicationGroupDescription" : hostname,
                "SecurityGroupIds" : security_groups
            },
            "DependsOn" : key + "SubnetGroup"
        }

        self.resources[key + "SubnetGroup"] = {
            "Type" : "AWS::ElastiCache::SubnetGroup",
            "Properties" : {
                "Description" : hostname,
                "SubnetIds" : subnets
            }
        }

        if len(parameters) > 0:
            self.resources[key]['Properties']['CacheParameterGroupName'] = Ref(key + 'ParameterGroup')

            if version.startswith("2.8"):
                cache_parameter_group_family = "redis2.8"
            elif version.startswith("3.2"):
                cache_parameter_group_family = "redis3.2"
            elif version.startswith("6.2"):
                cache_parameter_group_family = "redis6.x"
            else:
                raise Exception("Unknown CacheParameterGroupFamily for Redis version {}".format(version))

            self.resources[key + 'ParameterGroup'] = {
            "Type": "AWS::ElastiCache::ParameterGroup",
                "Properties": {
                    "CacheParameterGroupFamily" : cache_parameter_group_family ,
                    "Properties" : parameters,
                    "Description": "boss-redis-properties"
                }
            }

        self._add_record_cname(key, hostname, replication = True)

    def add_security_group(self, key, name, rules, vpc=Ref("VPC")):
        """Add SecurityGroup to the configuration

        Args:
            key (str) : Unique name for the resource in the template
            name (str) : The name to give the SecurityGroup
            rules (list) : A list of tuples (protocol, from port, to port, cidr)
                           Where protocol/from/to can be -1 if open access is desired
            vpc (str) : The VPC ID or Ref to add the Security Group to
        """
        ports = "/".join(map(lambda x: x[1] + "-" + x[2], rules))
        ingress = []
        for rule in rules:
            ingress.append({"IpProtocol" : rule[0], "FromPort" : rule[1], "ToPort" : rule[2], "CidrIp" : rule[3]})

        self.resources[key] = {
          "Type" : "AWS::EC2::SecurityGroup",
          "Properties" : {
            "VpcId" : vpc,
            "GroupDescription" : "Enable access to ports {}".format(ports),
            "SecurityGroupIngress" : ingress,
             "Tags" : [
                {"Key" : "Stack", "Value" : Ref("AWS::StackName") },
                {"Key" : "Name", "Value" : name }
            ]
          }
        }

    def add_route_table(self, key, name, vpc=Ref("VPC"), subnets=[Ref("Subnet")]):
        """Add RouteTable to the configuration

        Args:
            key (str) : Unique name for the resource in the template
            name (str) : The name to give the RouteTable
            vpc (str) : The VPC ID or Ref to add the RouteTable to
            subnets (list) : A list of Subnet IDs or Refs to attach the RouteTable to
        """
        self.resources[key] = {
          "Type" : "AWS::EC2::RouteTable",
          "Properties" : {
            "VpcId" : vpc,
            "Tags" : [
                {"Key" : "Stack", "Value" : Ref("AWS::StackName") },
                {"Key" : "Name", "Value" : name }
            ]
          }
        }

        for subnet in subnets:
            key_ = key + "SubnetAssociation" + str(subnets.index(subnet))
            self.add_route_table_association(key_, Ref(key), subnet)

    def add_route_table_association(self, key, route_table, subnet=Ref("Subnet")):
        """Add SubnetRouteTableAssociation to the configuration

        Args:
            key (str) : Unique name for the resource in the template
            route_table (str) : The unique name of the RouteTable in the configuration
            subnet (string|Ref) : The the unique name of the Subnet to associate the RouteTable with
        """
        self.resources[key] = {
          "Type" : "AWS::EC2::SubnetRouteTableAssociation",
          "Properties" : {
            "SubnetId" : subnet,
            "RouteTableId" : route_table
          }
        }

    def add_route_table_route(self, key, route_table, cidr="0.0.0.0/0", gateway=None, peer=None, instance=None, nat=None, depends_on=None):
        """Add a Route to the configuration

        Note: Only one of gateway/peer/instance should be specified for a call

        Args:
            key (str) : Unique name for the resource in the template
            route_table (str) : The RouteTable ID or Ref to add the Route to
            cidr (str) : A CIDR formatted (x.x.x.x/y) subnet of the route
            gateway (None|string) The the target InternetGateway ID or Ref
            peer (None|string) : The the target VPCPeerConnection ID or Ref
            instance (None|string) : The the target EC2 Instance ID or Ref
            depends_on (None|string|list): A unique name or list of unique names of resources within the
                                           configuration and is used to determine the launch order of resources
        """
        self.resources[key] = {
          "Type" : "AWS::EC2::Route",
          "Properties" : {
            "RouteTableId" : route_table,
            "DestinationCidrBlock" : cidr
          }
        }

        checks = [gateway, peer, instance, nat]
        if len(checks) - checks.count(None) != 1:
            raise Exception("Required to specify one and only one of the following arguments: gateway|peer|instance|nat")


        if gateway is not None:
            self.resources[key]["Properties"]["GatewayId"] = gateway
        if peer is not None:
            self.resources[key]["Properties"]["VpcPeeringConnectionId"] = peer
        if instance is not None:
            self.resources[key]["Properties"]["InstanceId"] = instance
        if nat is not None:
            self.resources[key]["Properties"]["NatGatewayId"] = nat

        if depends_on is not None:
            self.resources[key]["DependsOn"] = depends_on

    def add_internet_gateway(self, key, name, vpc=Ref("VPC")):
        """Add an InternetGateway to the configuration

        Args:
            key (str) : Unique name for the resource in the template
            name (str) : The name to give the InternetGateway
            vpc (str) : The VPC ID or Ref to add the InternetGateway to
        """
        self.resources[key] = {
          "Type" : "AWS::EC2::InternetGateway",
          "Properties" : {
            "Tags" : [
                {"Key" : "Stack", "Value" : Ref("AWS::StackName") },
                {"Key" : "Name", "Value" : name }
            ]
          }
        }

        if type(vpc) == dict:
            self.resources[key]['DependsOn'] = vpc['Ref']

        self.resources["Attach" + key] = {
           "Type" : "AWS::EC2::VPCGatewayAttachment",
           "Properties" : {
             "VpcId" : vpc,
             "InternetGatewayId" : Ref(key)
           },
           "DependsOn" : key
        }

    def add_vpc_peering(self, key, vpc, peer_vpc):
        """Add a VPCPeeringConnection to the configuration

        Args:
            key (str) : Unique name for the resource in the template
            vpc (str) : The VPC ID or Ref to create the peering connection from
            peer_vpc (str) : The VPC ID or Ref to create the peering connection to
        """
        self.resources[key] = {
            "Type" : "AWS::EC2::VPCPeeringConnection",
            "Properties" : {
                "VpcId" : vpc,
                "PeerVpcId" : peer_vpc,
                "Tags" : [
                    {"Key" : "Stack", "Value" : { "Ref" : "AWS::StackName"} }
                ]
            }
        }

    def add_app_loadbalancer(self, key, name, listeners, vpc_id=None, instances=None, subnets=None, security_groups=None,
                         healthcheck_path="/ping/", public=True, internal_dns=False, depends_on=None ):
        """
        Add an Application LoadBalancer to the configuration

        Args:
            key (str) : Unique name for the resource in the template
            name (str) : The name to give this elb
            listeners (list) : A list of tuples for the elb
                               (elb_port, instance_port, protocol [, ssl_cert_id])
                                   elb_port (str) : The port for the elb to listening on
                                   instance_port (str) : The port on the instance that the elb sends traffic to
                                   protocol (str) : The protocol used, ex: HTTP, HTTPS
                                   ssl_cert_id (Optional string) : The AWS ID of the SSL cert to use
            vpc_id (None|str) : Required unless directing traffic to a lambda
            instances (None|list) : A list of Instance IDs or Refs to attach to the LoadBalancer
            subnets (None|list) : A list of Subnet IDs or Refs to attach the LoadBalancer to
            security_groups (None|list) : A list of SecurityGroup IDs or Refs to apply to the LoadBalancer
            healthcheck_path (str) : The path used for for health checks Ex: "/alive/"
            public (bool) : If the ELB is public facing or internal
            internal_dns (bool) : If the ELB should have an internal Router53 entry
            depends_on (None|string|list): A unique name or list of unique names of resources within the
                                           configuration and is used to determine the launch order of resources

        Returns:
            (list) : List of CloudFormation template keys of the target groups created.
        """

        target_group_keys = []

        for ind, listener in enumerate(listeners):
            target_group_key = "{}TargetGroup".format(key)
            target_group_keys.append(target_group_key)

            using_https = len(listener) == 4 and listener[3] is not None

            self.resources[target_group_key] = {
                "Type": "AWS::ElasticLoadBalancingV2::TargetGroup",
                "Properties": {
                    "HealthCheckEnabled": True,
                    "HealthCheckPath": healthcheck_path,
                    "HealthCheckIntervalSeconds": 30,
                    "HealthCheckTimeoutSeconds": 5,
                    "HealthyThresholdCount": 2,
                    "UnhealthyThresholdCount": 5,
                    "Protocol": "HTTPS" if using_https else "HTTP",
                    "Port": listener[1],
                    "TargetType": "instance"
                }
            }

            if vpc_id is not None:
                self.resources[target_group_key]["Properties"]["VpcId"] = vpc_id

            listener_props = {
                "LoadBalancerArn": Ref(key),
                "Port": str(listener[0]),
                "Protocol": listener[2],
                "DefaultActions": [ {
                    "Type": "forward",
                    "TargetGroupArn": Ref(target_group_key)
                } ]
                #"InstancePort": str(listener[1]),
                #"SslPolicy": 'probably dont need to specify',
                #"PolicyNames": [key + "Policy"],
            }

            if using_https:
                listener_props["Certificates"] = [ { "CertificateArn": listener[3] } ]

            listener_key = "{}Listener{}".format(key, ind)
            self.resources[listener_key] = {
                "Type": "AWS::ElasticLoadBalancingV2::Listener",
                "Properties": listener_props
            }

            if using_https:
                # Redirect all requests to port 443.
                redirect_action = {
                    "Type": "redirect",
                    "RedirectConfig": {
                        "Protocol": "HTTPS",
                        "Port": "443",
                        "Host": "#{host}",
                        "Path": "/#{path}",
                        "Query": "#{query}",
                        "StatusCode": "HTTP_301"
                    }
                }
                self.resources["{}Listener{}Redirect".format(key, ind)] = {
                    "Type": "AWS::ElasticLoadBalancingV2::Listener",
                    "Properties": {
                        "LoadBalancerArn": Ref(key),
                        "DefaultActions": [redirect_action],
                        "Port": "80",
                        "Protocol": "HTTP"
                    }
                }


        self.resources[key] = {
            "Type": "AWS::ElasticLoadBalancingV2::LoadBalancer",
            "Properties": {
                "Type": "application",
                "Name": name.replace(".", "-"),  #elb names can't have periods in them
                "Scheme": "internet-facing" if public else "internal",
                "Tags": [
                    {"Key": "Stack", "Value": Ref("AWS::StackName")}
                ]
            }
        }

        if security_groups is not None:
            self.resources[key]["Properties"]["SecurityGroups"] = security_groups
        if subnets is not None:
            self.resources[key]["Properties"]["Subnets"] = subnets
        if depends_on is not None:
            self.resources[key]["DependsOn"] = depends_on

        # Most ELB front ASGs that are generating their own DNS records
        if internal_dns:
            self._add_record_cname(key, name, elb = True)

        return target_group_keys


    def add_loadbalancer(self, key, name, listeners, instances=None, subnets=None, security_groups=None,
                         healthcheck_target="HTTP:80/ping/", public=True, internal_dns=False, depends_on=None ):
        """
        Add a Classic LoadBalancer to the configuration

        Args:
            key (str) : Unique name for the resource in the template
            name (str) : The name to give this elb
            listeners (list) : A list of tuples for the elb
                               (elb_port, instance_port, protocol [, ssl_cert_id])
                                   elb_port (str) : The port for the elb to listening on
                                   instance_port (str) : The port on the instance that the elb sends traffic to
                                   protocol (str) : The protocol used, ex: HTTP, HTTPS
                                   ssl_cert_id (Optional string) : The AWS ID of the SSL cert to use
            instances (None|list) : A list of Instance IDs or Refs to attach to the LoadBalancer
            subnets (None|list) : A list of Subnet IDs or Refsto attach the LoadBalancer to
            security_groups (None|list) : A list of SecurityGroup IDs or Refs to apply to the LoadBalancer
            healthcheck_target (str) : The URL used for for health checks Ex: "HTTP:80/"
            public (bool) : If the ELB is public facing or internal
            internal_dns (bool) : If the ELB should have an internal Router53 entry
            depends_on (None|string|list): A unique name or list of unique names of resources within the
                                           configuration and is used to determine the launch order of resources
        """

        listener_defs = []
        for listener in listeners:
            listener_def = {
                "LoadBalancerPort": str(listener[0]),
                "InstancePort": str(listener[1]),
                "Protocol": listener[2],
                "PolicyNames": [key + "Policy"],
            }

            if len(listener) == 4 and listener[3] is not None:
                listener_def["SSLCertificateId"] = listener[3]
            listener_defs.append(listener_def)


        self.resources[key] = {
            "Type": "AWS::ElasticLoadBalancing::LoadBalancer",
            "Properties": {
                "CrossZone": True,
                "HealthCheck": {
                    "Target": healthcheck_target,
                    "HealthyThreshold": "2",
                    "UnhealthyThreshold": "5",
                    "Interval": "30",
                    "Timeout": "5"
                },
                "LBCookieStickinessPolicy" : [{"PolicyName": key + "Policy"}],
                "LoadBalancerName": name.replace(".", "-"),  #elb names can't have periods in them
                "Listeners": listener_defs,
                "Scheme": "internet-facing" if public else "internal",
                "Tags": [
                    {"Key": "Stack", "Value": Ref("AWS::StackName")}
                ]
            }
        }

        if instances is not None:
            self.resources[key]["Properties"]["Instances"] = instances
        if security_groups is not None:
            self.resources[key]["Properties"]["SecurityGroups"] = security_groups
        if subnets is not None:
            self.resources[key]["Properties"]["Subnets"] = subnets
        if depends_on is not None:
            self.resources[key]["DependsOn"] = depends_on

        # self.resources["Outputs"] = {
        #     "URL" : {
        #         "Description": "URL of the ELB website",
        #         "Value":  { "Fn::Join": ["", ["http://", {"Fn::GetAtt": [ "ElasticLoadBalancer", "DNSName"]}]]}
        #     }
        # }

        # Most ELB front ASGs that are generating their own DNS records
        if internal_dns:
            self._add_record_cname(key, name, elb = True)

    def add_autoscale_group(self, key, hostname, ami, keypair, subnets=[Ref("Subnet")], type_="t2.micro", public_ip=False,
                            security_groups=[], user_data=None, min=1, max=1, elb=None, notifications=None,
                            role=None, health_check_grace_period=30, support_update=True, detailed_monitoring=False,
                            target_group_arns=None, depends_on=None):
        """Add an AutoScalingGroup to the configuration

        Args:
            key (str) : Unique name for the resource in the template
            hostname (str) : The hostname / instance name of the instances
            ami (str) : The AMI ID of the image to base the instances on
            subnets (list) : A list of Subnet IDs or Refs to launch the instances in
            type_ (str) : The instance type to create
            public_ip (bool) : Should the instances gets public IP addresses
            security_groups (list) : A list of SecurityGroup IDs or Refs to apply to the instances
            user_data (None|str) : A string of user-data to give to the instance when launching
            min (int|str) : The minimimum number of instances in the AutoScalingGroup
            max (int|str) : The maximum number of instances in the AutoScalingGroup
            elb (None|str) : The LoadBalancer ID or Ref to attach the AutoScalingGroup to
            notifications (None|List|str) : list or single topic ARN or Ref to send ASG notifications to
            role (None|str) : Role name to use when creating instances
            health_check_grace_period (int) : grace period in seconds to wait before checking newly created instances.
            support_update (bool) : If the ASG should include RollingUpdate UpdatePolicy
            detailed_monitoring (bool) : Enable detailed monitoring of the instances. False means 5 minute statistics.
            target_group_arns (None|str|list): Place instances in the given target group(s) (used with app load balancers).
            depends_on (None|str|list): A unique name or list of unique names of resources within the
                                           configuration and is used to determine the launch order of resources
        """

        commit = None
        if type(ami) == tuple:
            commit = ami[1]
            ami = ami[0]

        self.resources[key] = {
            "Type" : "AWS::AutoScaling::AutoScalingGroup",
            "Properties" : {
                "DesiredCapacity" : min, # Initial capacity, will min size also ensure the size on startup?
                "HealthCheckType" : "EC2" if elb is None else "ELB",
                "HealthCheckGracePeriod" : health_check_grace_period, # seconds
                "LaunchConfigurationName" : Ref(key + "Configuration"),
                "LoadBalancerNames" : [] if elb is None else [elb],
                "MaxSize" : str(max),
                "MinSize" : str(min),
                "Tags" : [
                    {"Key" : "Stack", "Value" : Ref("AWS::StackName"), "PropagateAtLaunch": "true" },
                    {"Key" : "Name", "Value" : hostname, "PropagateAtLaunch": "true" }
                ],
                "VPCZoneIdentifier" : subnets
            }
        }

        if support_update:
            self.resources[key]["UpdatePolicy"] = {
                "AutoScalingRollingUpdate" : {
                    "MinInstancesInService" : str(min - 1), # Restart one instance at a time
                    "MaxBatchSize": "1",
                    #"WaitOnResourceSignals": "true", # need to have instances signal ready...
                    #"PauseTime": "PT5M" # 5 minutes
                },
                "AutoScalingScheduledAction" : {
                    "IgnoreUnmodifiedGroupSizeProperties" : "true"
                }
            }

        if notifications is not None:
            if type(notifications) != list:
                notifications = [notifications]
            self.resources[key]["Properties"]["NotificationConfigurations"] = [
                {
                    "NotificationTypes": [
                        "autoscaling:EC2_INSTANCE_LAUNCH",
                        "autoscaling:EC2_INSTANCE_LAUNCH_ERROR",
                        "autoscaling:EC2_INSTANCE_TERMINATE",
                        "autoscaling:EC2_INSTANCE_TERMINATE_ERROR",
                        "autoscaling:TEST_NOTIFICATION"
                    ],
                    "TopicARN" : topic
                } for topic in notifications
            ]

        if target_group_arns is not None:
            self.resources[key]["Properties"]["TargetGroupARNs"] = target_group_arns

        if depends_on is not None:
            self.resources[key]["DependsOn"] = depends_on

        self.resources[key + "Configuration"] = {
            "Type" : "AWS::AutoScaling::LaunchConfiguration",
            "Properties" : {
                "AssociatePublicIpAddress" : public_ip,
                #"EbsOptimized" : Boolean, EBS I/O optimized
                "ImageId" : ami,
                "InstanceMonitoring" : detailed_monitoring, # CloudWatch Monitoring...
                "InstanceType" : type_,
                "KeyName" : keypair,
                "SecurityGroups" : security_groups,
                "UserData" : "" if user_data is None else { "Fn::Base64" : user_data }
            }
        }

        if role is not None:
            self.resources[key + "Configuration"]["Properties"]["IamInstanceProfile"] = role

        if commit is not None:
            kv = {"Key": "AMI Commit", "Value": commit, "PropagateAtLaunch": "true"}
            self.resources[key]["Properties"]["Tags"].append(kv)

        self.keypairs[hostname] = keypair

        _hostname = Arg.String(key + "Hostname", hostname,
                               "Hostname of the EC2 Instance '{}'".format(key))
        self.add_arg(_hostname)

    def add_autoscale_policy(self, key, asg, warmup=60, adjustments=[], alarms=[], period=2):
        """Add an AutoScalingGroup AutoScale Policy to the configuration

        Args:
            key (str) : Unique name for the resource in the template
            asg (str): AutoScaleGroup ID or Ref of the ASG to scale
            warmup (int): Number of seconds estimated for a new machine to boot
                          and start processing data
            adjustments (list): List of tuples of (lower, upper, step) that defined
                                when and how machine machines to scale
                                lower (int|float|None): Lower bound of adjustment step
                                upper (int|float|None): Upper bound of adjustment step
                                step (int): Number of machines to scale by
            alarms (list): List of tuples of (metric, statistic, comparison, threashold)
                           which are passed to add_cloudwatch_alarm() to create the alarms
                           that will trigger the adjustments actions
            period (int): Number of 60 second periods over which the alarm metrics are evaluated
        """
        adjustments_ = []
        for lower, upper, step in adjustments:
            adjustment = {"ScalingAdjustment": step}
            if lower is not None:
                adjustment["MetricIntervalLowerBound"] = lower
            if upper is not None:
                adjustment["MetricIntervalUpperBound"] = upper
            adjustments_.append(adjustment)

        self.resources[key] = {
            "Type" : "AWS::AutoScaling::ScalingPolicy",
            "Properties" : {
                "AutoScalingGroupName" : asg,
                "AdjustmentType" : "ChangeInCapacity",
                "PolicyType" : "StepScaling",
                "EstimatedInstanceWarmup" : warmup,
                #"MetricAggregationType" : "Minimum|Maximum|Average", # Default Average
                #"MetricsCollection" : [{"Granularity":"1Minute", "Metrics":[]}]
                "StepAdjustments" : adjustments_
            }
        }

        i = 0
        for metric, statistic, comparison, threashold in alarms:
            i += 1
            self.add_cloudwatch_alarm(key + "Alarm{}".format(i), "",
                                      metric, statistic, comparison, threashold,
                                      [Ref(key)], # alarm_actions
                                      {"AutoScalingGroupName": asg}, # dimensions
                                      period = period,
                                      namespace = "AWS/EC2")

    def add_s3_bucket(self, key, name, access_control=None, life_cycle_config=None, notification_config=None, encryption=None, tags=None, depends_on=None):
        """Create or configure a S3 bucket.

        Bucket is configured to never be deleted for safety reasons.

        Args:
            key (str): Unique name for the resource in the template.
            name (str): Bucket name.
            access_control (optional[string]): A canned access control list (see Canned ACL in S3 docs).
            life_cycle_config (optional[dict]): Life cycle configuration object.
            notification_config (optional[dict]): Optionally send notification to lamba function/SQS/SNS.
            encryption (optional[dict]): Optional Server Side Encryption Configuration information for protecting
                                         data in the S3 bucket
            tags (optional[dict]): Optional key-value pairs to add to bucket.
            depends_on (optional[string]): Optional key of resource bucket depends on.

        """
        self.resources[key] = {
            "Type": "AWS::S3::Bucket",
            "Properties": {
                "BucketName": name
            },
            "DeletionPolicy": "Retain"
        }

        if depends_on is not None:
            self.resources[key]['DependsOn'] = depends_on

        if access_control is not None:
            self.resources[key]['Properties']['AccessControl'] = access_control

        if life_cycle_config is not None:
            self.resources[key]['Properties']['LifecycleConfiguration'] = life_cycle_config

        if notification_config is not None:
            self.resources[key]['Properties']['NotificationConfiguration'] = notification_config

        if encryption is not None:
            self.resources[key]['Properties']['BucketEncryption'] = encryption

        if tags is not None:
            self.resources[key]['Properties']['Tags'] = tags


    def add_s3_bucket_policy(self, key, bucket_name, action, principal, bucket_only=False):
        """Add permissions to an S3 bucket.

        Args:
            key (str): Unique name for the resource in the template.
            bucket_name (string|dict): Bucket name or CloudFormation instrinsic function to determine name (example: {"Ref": "mybucket"}).
            action (list): List of strings for the types of actions to allow.
            principal (dict): Dictionary identifying the entity given permission to the S3 bucket.
            bucket_only (Optional[bool]): If True, don't append /* to the bucket name.  Defaults to False.
        """

        bucket_arn = ['arn:aws:s3:::', bucket_name]
        if not bucket_only:
            # Actions apply to the bucket's objects.
            bucket_arn.append('/*')

        self.resources[key] = {
            'Type': 'AWS::S3::BucketPolicy',
            'Properties': {
                'Bucket': bucket_name,
                'PolicyDocument': {
                    'Statement': [
                        {
                            'Action': action,
                            'Effect': 'Allow',
                            'Resource': { 'Fn::Join': ['', bucket_arn]},
                            'Principal': principal
                        }
                    ]
                }
            }
        }


    def append_s3_bucket_policy(self, key, bucket_name, action, principal, bucket_only=False):
        """Add an additional action-principal pair to a bucket.

        Args:
            key (string): Existing name for the resource in the template.
            bucket_name (string|dict): Bucket name or CloudFormation instrinsic function to determine name (example: {"Ref": "mybucket"}).
            action (list): List of strings for the types of actions to allow.
            principal (dict): Dictionary identifying the entity given permission to the S3 bucket.
            bucket_only (Optional[bool]): If True, don't append /* to the bucket name.  Defaults to False.
        """
        if key not in self.resources:
            raise ValueError(key + " doesn't exist, cannot append to")

        if self.resources[key]['Type'] != 'AWS::S3::BucketPolicy':
            raise ValueError(key + " is not an S3 bucket policy")

        if self.resources[key]['Properties']['Bucket'] != bucket_name:
            raise ValueError(key + " is not an S3 bucket policy for bucket: " + bucket_name)

        bucket_arn = ['arn:aws:s3:::', bucket_name]
        if not bucket_only:
            # Actions apply to the bucket's objects.
            bucket_arn.append('/*')

        self.resources[key]['Properties']['PolicyDocument']['Statement'].append(
            {
                'Action': action,
                'Effect': 'Allow',
                'Resource': { 'Fn::Join': ['', bucket_arn]},
                'Principal': principal
            })


    def add_lambda(self, key, name, role, file=None, handler=None, s3=None, description="", memory=128, timeout=3, security_groups=None, subnets=None, depends_on=None, runtime="python3.7", reserved_executions=None, dlq=None, layers=None):
        """Create a Python Lambda

        Args:
            key (str) : Unique name for the resource in the template
            name (str) : Function name
            role (str) : IAM role the lambda will execute under
            file (None|string) : File path to file containing lambda source code
            handler (None|string) : Name of lambda's handler function (the entry point).  If using a file, than the handler should be 'index.<name of function>'.  If `file` is not provided the lambda package is built and uploaded to S3.
            s3 (None|tuple) : Tuple (bucket, key, handler) for the S3 location containing lambda source code
                              handler is the Python function to execute
            description (str) : Lambda description
            memory (str|int) : Amount of memory (MB) to execute the lambda with
                                  Note, CPU is linked to the amount of memory allocated
            timeout (str|int) : Execution timeout (Seconds)
            security_groups (None|list) : List of ids of security groups to grant the lambda access to
            subnets (None|list) : List of ids of subnets to grant the lambda access to
            depends_on (None|str|list) : A unique name or list of unique names of resources within the
                                            configuration and is used to determine the launch order of resources
            runtime (optional[str]) : Lambda runtime to use.  Defaults to "python3.7".  Ignored if handler is not None, but file and s3 are None.
            reserved_executions (optional[int]): Number of reserved concurrent executions for the lambda.
            dlq (optional[str]): ARN of dead letter queue.  Defaults to None.
            layers (optional[list[str]]): List of lambda layer ARNs with version
        """

        if file is not None:
            minified_file = utils.python_minifiy(file)
            with open(minified_file, "r") as fh:
                # Warning, sanitizing process does not handle backslashes
                # in strings properly!
                code = utils.json_sanitize(fh.read())
                if len(code) >= 4096:
                    raise Exception("Lambda code file is too large") # TODO need to figure out if / how to upload a manually created zip file

            code = {"ZipFile": code}
            if handler is None:
                handler = "index.handler"
        elif s3 is not None:
            bucket, s3key, handler = s3
            code = {
                "S3Bucket": bucket,
                "S3Key": s3key
            }
        elif handler is not None:
            s3, runtime, layers = lambdas.s3_config(self.bosslet_config, name, handler)
            bucket, s3key, handler = s3
            code = {
                "S3Bucket": bucket,
                "S3Key": s3key
            }
        else:
            raise Exception("Need source file or S3 bucket or S3 package handler")

        memory = int(memory)
        if memory < 128 or 3008 < memory:
            raise Exception("Lambda memory should be between 128 and 3008")
        if memory % 64 != 0:
            raise Exception("Lambda memory should be a multiple of 64")

        self.resources[key] = {
            "Type" : "AWS::Lambda::Function",
            "Properties" : {
                "Code": code,
                "Description": description,
                "FunctionName": name,
                "Handler": handler,
                "MemorySize": memory,
                "Role": role,
                "Runtime": runtime,
                "Timeout": int(timeout)
            }
        }

        if security_groups is not None and subnets is not None:
            self.resources[key]["Properties"]["VpcConfig"] = {
                "SecurityGroupIds": security_groups,
                "SubnetIds": subnets
            }
        elif security_groups is not None or subnets is not None:
            raise Exception("security_groups and subnets should both be specified")

        if depends_on is not None:
            self.resources[key]["DependsOn"] = depends_on

        if reserved_executions is not None:
            self.resources[key]['Properties']['ReservedConcurrentExecutions'] = reserved_executions

        if dlq is not None:
            self.resources[key]['Properties']['DeadLetterConfig'] = {'TargetArn': dlq}

        if reserved_executions is not None:
            self.resources[key]['Properties']['ReservedConcurrentExecutions'] = reserved_executions

        if layers is not None:
            self.resources[key]['Properties']['Layers'] = layers

    def add_lambda_permission(self, key, lambda_, action="lambda:invokeFunction", principal="sns.amazonaws.com", source=None, depends_on=None):
        """Add permissions to a Lambda (typically to allow another resource to invoke the lambda)

        Args:
            key (str) : Unique name for the resource in the template
            lambda_ (str) : Lambda ID or Ref to add the permission to
            action (str) : Permission action to grant the lambda
            principal (str) : AWS principal to grant the action to
            source (str) : Source ARN to restrict the permission to
            depends_on (optional[string]): Optional key of resource that permission depends on.
        """
        self.resources[key] = {
            "Type": "AWS::Lambda::Permission",
            "Properties": {
                "Action": action,
                "FunctionName": lambda_,
                "Principal": principal
            }
        }

        if source is not None:
            self.resources[key]["Properties"]["SourceArn"] = source

        if depends_on is not None:
            self.resources[key]['DependsOn'] = depends_on

    def add_lambda_event_source(self, key, event_source_arn, function_name,
                                batch_size=None, enabled=True):
        """Connect lambda to an event source.

        Args:
            key (str) : Unique name for the resource in the template.
            event_source_arn (str): Arn of the event source to connect to lambda.
            function_name (str): Name of lambda function to connect.
            batch_size (Optional[int]): If not provided, default depends on event source type.
            enabled (Optional[bool]): Defaults to enabled.
        """
        self.resources[key] = {
            "Type": "AWS::Lambda::EventSourceMapping",
            "Properties": {
                "Enabled": enabled,
                "EventSourceArn": event_source_arn,
                "FunctionName": function_name,
            }
        }

        if batch_size is not None:
            self.resources[key]["Properties"]["BatchSize"] = batch_size

    def _add_record_cname(self, key, hostname, vpc=Ref("VPC"), ttl="300", rds=False, cluster=False, replication=False, ec2=False, elb=False):
        """Add a CNAME RecordSet to the configuration

        Note: Only one of rds/cluster/replication/ec2 should be specified for the call
        Note: cluster is not currently supported, due to Fn::GetAtt not working on ElastiCache Redis Cluster instances

        Args:
            key (str) : Unique name for the resource in the template to create the RecordSet for
            hostname (str) : The DNS hostname to map to the resource
            vpc (str) : The VPC ID or Ref containing the target HostedZone
            ttl (str) : The Time to live for the RecordSet
            rds (bool) : The key is a RDS instance
            cluster (bool) : The key is a ElastiCache Cluster instance
            replication (bool) : The key is a ElastiCache ReplicationGroup instance
            ec2 (bool) : The key is a EC2 instance
            elb (bool) : The key is a ELB
        """
        address_key = None
        if rds:
            address_key = "Endpoint.Address"
        elif cluster:
            address_key = "ConfigurationEndpoint.Address" # Only works for memcached db
            raise Exception("NotSupported currently")
        elif replication:
            address_key = "PrimaryEndPoint.Address"
        elif ec2: # Could create an A record type, with PrivateIP as the key
            address_key = "PrivateDnsName"
        elif elb:
            address_key = "DNSName"

        if address_key is None:
            raise Exception("Unknown type of CNAME record to create")

        zone = self.vpc_domain + "."
        target = { "Fn::GetAtt" : [ key, address_key ] }

        self.add_route_53_record_set(key + "Record", hostname, target, zone, ttl)

        if "DNSZone" in self.resources:
            self.resources[key + "Record"]["DependsOn"] = "DNSZone"

    def add_route_53_record_set(self, key, full_domain_name, cname_value, hosted_zone_name, ttl=300):
        """Add a CNAME RecordSet to the configuration

        Args:
            key (str) : Unique name for the resource in the template to create the RecordSet for
            full_domain_name (str) : The FQDN DNS entry to create
            cname_value (str) : The CNAME value to return for the full_domain_name
            hosted_zone_name (str) : The name of the HostedZone (should end in a '.')
            ttl (int|string) : The Time to live for the RecordSet

        """
        self.resources[key] = {
            "Type": "AWS::Route53::RecordSet",
            "Properties": {
                "HostedZoneName": hosted_zone_name,
                'Name': full_domain_name,
                'Type': 'CNAME',
                'ResourceRecords': [cname_value],
                'TTL': ttl,
            }
        }

    def add_public_dns(self, target_key, public_hostname, elb=True):
        """Add a CNAME RecordSet to the configuration

        Adds a CNAME RecordSet to the EXTERNAL_DOMAIN Route53 Hosted Zone

        Args:
            target_key (str) : Unique name for the resource in the template to create the RecordSet for
            public_hostname (str) : The DNS hostname to map to the resource
            elb (bool) : The key is an ELB
        """
        address_key = None
        if elb:
            address_key = "DNSName"

        if address_key is None:
            raise Exception("Unknown type of CNAME record to create")

        zone = self.bosslet_config.EXTERNAL_DOMAIN + "."
        target = { "Fn::GetAtt" : [ target_key, address_key ] }

        self.resources[target_key + "Record"] = {
            "Type": "AWS::Route53::RecordSet",
            "Properties": {
                "HostedZoneName": zone,
                'Name': public_hostname,
                'Type': 'CNAME',
                'ResourceRecords': [target],
                'TTL': 300,
            }
        }

    def add_cloudwatch_rule(
        self, key, targets, name=None, event=None, schedule=None, role_arn=None, description=None, depends_on=None, enable=True):
        """Add an rule that routes CloudWatch Events to target(s).

        Note that event and schedule cannot both be None.

        Args:
            key (str): Unique name for the resource in CloudFormation template.
            targets (list): List of dicts with keys: Arn, Id, and optionally, Input and InputPath.  See Amazon CloudWatch Events Rule Target documentation.
            name (optional[dict]): Name for rule.  One will be auto-generated if this isn't provided.
            event (optional[dict]): See Amazon Events and Event Patterns documentation.
            schedule (optional[string]): See Amazon Schedule Expression Syntax for Rules documentation.
            role_arn (optional[string]): Role to assign to rule so it can invoke the target(s).
            description (optional[string]): Description of rule, defaults to None.
            depends_on (optional[string|list]) : A unique name or list of unique names of resources that should be created first.
            enable (optional[bool]) Whether rule should be enabled when created.

        Raises:
            (exception): When neither event or schedule are provided.
        """
        if event is None and schedule is None:
            raise Exception('event and schedule cannot both be None.')

        props = { 'Targets': targets }

        if enable:
            props['State'] = 'ENABLED'
        else:
            props['State'] = 'DISABLED'

        if name is not None:
            props['Name'] = name

        if description is not None:
            props['Description'] = description

        if schedule is not None:
            props['ScheduleExpression'] = schedule

        if event is not None:
            props['EventPattern'] = event

        if role_arn is not None:
            props['RoleArn'] = role_arn

        self.resources[key] = {
            'Type': 'AWS::Events::Rule',
            'Properties': props
        }

        if depends_on is not None:
            self.resources[key]['DependsOn'] = depends_on

    def add_cloudwatch_alarm(self, key, description, metric, statistic, comparison, threashold, alarm_actions, dimensions={}, period=5, namespace="AWS/ELB", depends_on=None):
        """Add CloudWatch Alarm for a LoadBalancer

        Args:
            key (str) : Unique name for the resource in the template
            description (str) : Alarm description
            metric (str) : Statistic metric
            statistic (str) : Alarm statistic (SampleCount|Average|Sum|Minimum|Maximum)
            comparison (str) : Alarm's comparison operation
            threashold (str) : Threashold limit
            alarm_actions (list) : List of ARN string of actions to execute when the alarm is triggered
            dimensions (dict) : Dictionary of dimensions for the alarm's associated metric
            period (int) : Number of 60 second periods over which the metric is evaluated
            namespace (str) : AWS Namespace of the alarm metric (default AWS/ELB)
            depends_on (None|string|list): A unique name or list of unique names of resources within the
                                           configuration and is used to determine the launch order of resources
        """
        self.resources[key] = {
              "Type": "AWS::CloudWatch::Alarm",
              "Properties": {
                "ActionsEnabled": "true",
                "AlarmDescription": description,
                "ComparisonOperator": comparison,
                "EvaluationPeriods": str(period),
                "MetricName": metric,
                "Namespace": namespace,
                "Period": "60",
                "Statistic": statistic,
                "Threshold": threashold,
                "AlarmActions": alarm_actions,
                "Dimensions": [{"Name": k, "Value": v} for k,v in dimensions.items()]
              }
        }

        if depends_on is not None:
            self.resources[key]["DependsOn"] = depends_on

    # XXX: are alarm_actions unique keys from the configuration?
    def add_cloudwatch(self, lb_name, alarm_actions, depends_on=None ):
        """ Add CloudWatch Alarms for LoadBalancer

        Adds CloudWatch Alarms for Latency, SurgeCount, and UnhealthyHostCount for an ELB

        Args:
            lb_name (str) : The LoadBalancer name
            alarm_actions (str) : The name of SNS mailing list
            depends_on (None|string|list): A unique name or list of unique names of resources within the
                                           configuration and is used to determine the launch order of resources
        """
        self.add_cloudwatch_alarm("Latency", "",
                                  "Latency", "Average", "GreaterThanOrEqualToThreshold", "10.0",
                                  alarm_actions, {"LoadBalancerName": lb_name}, depends_on=depends_on)

        self.add_cloudwatch_alarm("SurgeCount", "Surge Count in Load Balance",
                                  "SurgeQueueLength", "Average", "GreaterThanOrEqualToThreshold", "3.0",
                                  alarm_actions, {"LoadBalancerName": lb_name}, depends_on=depends_on)

        self.add_cloudwatch_alarm("UnhealthyHostCount", "Unhealthy Host Count in Load Balance",
                                  "UnHealthyHostCount", "Minimum", "GreaterThanOrEqualToThreshold", "1.0",
                                  alarm_actions, {"LoadBalancerName": lb_name}, depends_on=depends_on)

    def add_sns_topic(self, key, name, topic, subscriptions=[]):
        """Create a SNS topic

        Args:
            key (str) : Unique name for the resource in the template
            name (str): Display name of the SNS topic
            topic (str): SNS topic name
            subscriptions (list): List of tuples containing SNS subscriptions to create
                                  (protocol, endpoint)
        """
        self.resources[key] = {
            "Type": "AWS::SNS::Topic",
            "Properties": {
                "DisplayName": name,
                "Subscription": [{"Endpoint": ep, "Protocol": pt} for pt, ep in subscriptions],
                "TopicName": topic,
            }
        }


    def add_sqs_queue(self, key, name, hide=30, retention=5760, dead=None):
        """Create a SQS Queue

        Notes:
            Maximum message size is 256KiB, which is the maximum size for SQS

        Args:
            key (str) : Unique name for the resource in the template
            name (str): Display name of the SQS queue
            hide (int) : Number of seconds to hide a queue item before it is again available for processing
            retention (int) : Number of minute a message will be retained
                              Limits are 1 minute to 14 days (default 4 days)
            dead (None|tuple) : Dead letter queue tuple (targetARN, missedDeliveries)
        """

        if retention < 1 or retention > 20160:
            raise Exception("Rentention period is 1 minute to 14 days")

        self.resources[key] = {
            "Type": "AWS::SQS::Queue",
            "Properties": {
                "MessageRetentionPeriod": int(retention) * 60,
                "QueueName": name,
                "VisibilityTimeout": int(hide)
            }
        }

        if dead is not None:
            arn, missed = dead
            self.resources[key]["Properties"]["RedrivePolicy"] = {
                "deadLetterTargetArn": arn,
                "maxReceiveCount": missed
            }

    def add_sqs_policy(self, key, name, queues_list, role):
        """Add full access for the given role to the given queues.

        Example call:

        self.add_sqs_policy(
            'SqsPolicy', 'sqs_policy',
            [Ref('S3Flush'), Ref('DeadLetter')],
            'endpoint')

        Note that the use of 'Ref' in the queue_list.  This lets you use the
        name of the queue rather than the full URL of the queue.

        Args:
            key (str): Lookup key for this SQS policy.
            name (str): Id for this SQS policy.
            queues_list (list): List of Queue IDs or Refs to apply policy to.
            role (str): Give this IAM role full access to these queues.
        """

        self.resources[key] = {
            'Type': 'AWS::SQS::QueuePolicy',
            'Properties': {
                'PolicyDocument': {
                    'Id': name,
                    'Version': '2012-10-17',
                    'Statement': [{
                        'Sid': 'Grant-Full-Access',
                        'Effect': 'Allow',
                        'Principal': { 'AWS': role },
                        'Action': ['sqs:*'],
                        'Resource': '*'
                    }]
                },
                'Queues': queues_list
            }
        }

    def add_event_rule(self, key, name, role_arn=None, schedule_expression=None, event_pattern=None, state=None,
                       target_list=None, description=None):
        """

        Args:
            key (str) : Unique name for the resource in the template
            name (str): Display name of the event rule
            role_arn (str): ARN of role this event will use
            schedule_expression (str): string expression of how often this rule will run.
            event_pattern (JSON object):  describes which events CloudWatch Events routes to the specified target
            state (str): indicates whether the rule is enabled
            target_list: List of targets to forward events to.
            description: Description of the event rule.

        Raises:
            (exception): When neither schedule_expression or event_pattern are provided.

        """
        if schedule_expression is None and event_pattern is None:
            raise Exception("schedule_expression and event_pattern cannot both be None.")

        self.resources[key] = {
            "Type": "AWS::Events::Rule",
            "Properties": {
                "Name": name,
            }
        }
        if role_arn is not None:
            self.resources[key]["Properties"]["RoleArn"] = role_arn
        if schedule_expression is not None:
            self.resources[key]["Properties"]["ScheduleExpression"] = schedule_expression
        if event_pattern is not None:
            self.resources[key]["Properties"]["EventPattern"] = event_pattern
        if state is not None:
            self.resources[key]["Properties"]["State"] = state
        if target_list is not None:
            self.resources[key]["Properties"]["Targets"] = target_list
        if description is not None:
            self.resources[key]["Properties"]["Description"] = description

    def add_kms_key(self, key, alias, key_users, user_actions):
        """Add a KMS Key

        Note: KMS Key permissions are a little different from the rest of AWS
              resources. User's must be given permission to use a key and by
              default they don't have permissions.

        Args:
            key (str): Unique name for the resource in the template
            alias (str): Name of the key to be created
            key_users (str|list[str]): ARN or list or ARNs of the users with permission
                                       to use the key
            user_actions (list[str]): List of KMS actions that the given user(s) are allows
                                      to perform with the key
        """
        account_id = self.bosslet_config.ACCOUNT_ID

        self.resources[key] = {
            "Type": "AWS::KMS::Key",
            "Properties": {
                "Description": "KMS Key for {}".format(alias),
                "KeyPolicy": {
                    "Id": alias,
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "Enable IAM User Permissions",
                            "Effect": "Allow",
                            "Principal": {
                                "AWS": "arn:aws:iam::{}:root".format(account_id)
                            },
                            "Action": "kms:*",
                            "Resource": "*"
                        },
                        {
                            "Sid": "Allow use of the key",
                            "Effect": "Allow",
                            "Principal": { "AWS": key_users },
                            "Action": user_actions,
                            "Resource": "*"
                        },
                    ]
                }
            }
        }

        self.resources[key + "Alias"] = {
            "Type": "AWS::KMS::Alias",
            "Properties": {
                "AliasName": "alias/" + alias.replace('.', '-'),
                "TargetKeyId": Ref(key),
            }
        }

    def add_data_pipeline(self, key, name, objects, description="", depends_on=None):
        """Add a Data Pipeline definition

        Args:
            key (str): Unique name for the resource in the template
            name (str): Name of the Data Pipeline to create
            objects (obj): The results of lib.datapipeline.DataPipeline().objects
                           after building the pipeline
            description (str): Description for the Data Pipeline
            depends_on (None|string|list): A unique name or list of unique names of resources within the
        """

        self.resources[key] = {
            "Type" : "AWS::DataPipeline::Pipeline",
            "Properties" : {
                "Activate" : True,
                "Description" : description,
                "Name" : name,
                "ParameterObjects" : [],
                "ParameterValues" : [],
                "PipelineObjects" : objects,
                "PipelineTags" : [],
            }
        }

        if depends_on is not None:
            self.resources[key]['DependsOn'] = depends_on

    def add_custom_resource(self, key, name, token, depends_on=None, **properties):
        self.resources[key] = {
            "Type": "Custom::{}".format(name),
            "Properties": {
                "ServiceToken": token,
                **properties
            }
        }

        if depends_on is not None:
            self.resources[key]['DependsOn'] = depends_on

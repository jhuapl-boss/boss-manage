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
import io
import configparser
import hosts
import library as lib

def get_scenario(var, default = None):
    """Handle getting the appropriate value froma variable using the SCENARIO
    environmental variable.

    A common method that will corrently handle decoding the (potential) dictionary
    of variable values and selecting the correct on based on the SCENARIO environmental
    variable.

    If the key defined in SCENARIO doesn't exist in the variable dictionary, the
    key "default" is used, and if that key is not defined, the default argument
    passed to the function is used.

    If var is not a dict, then it is returned without any change

    Args:
        var : The variable to (potentially) figure out the SCENARIO version for
        default : Default value if var is a dict and don't have a key for the SCENARIO

    Returns
        object : The variable or the SCENARIO version of the variable
    """
    scenario = os.environ["SCENARIO"]
    if type(var) == dict:
        var_ = var.get(scenario, None)
        if var_ is None:
            var_ = var.get("default", default)
    else:
        var_ = var
    return var_

def bool_str(val):
    """CloudFormation Template formatted boolean string.

    CloudFormation uses all lowercase for boolean values, which means that
    str() will not work correctly for boolean values.

    Args:
        val (bool) : Boolean value to convert to a string

    Returns:
        (string) : String of representing the boolean value
    """
    return "true" if val else "false"

class Arg:
    """Class of static methods to create the CloudFormation template argument
    snippits.
    """

    def __init__(self, key, parameter, argument):
        """Generic constructor used by all of the specific static methods.

        Args:
            key (string) : Unique name associated with the argument
            parameter (dict) : Dictionary of parameter information, as defined
                               by CloudFormation / AWS.
            argument (dict) : Dictionary of the argument to supply for the
                              parameter when launching the template
        """
        self.key = key
        self.parameter = parameter
        self.argument = argument

    @staticmethod
    def String(key, value, description=""):
        """Create a String argument.

        Args:
            key (string) : Unique name associated with the argument
            value (string) : String value
            description (string) : Argument description, only seen if manually
                                   launching the template
        """
        parameter =  {
            "Description" : description,
            "Type": "String"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)

    @staticmethod
    def Password(key, value, description=""):
        """Create a String argument that does not show typed characters.

        Args:
            key (string) : Unique name associated with the argument
            value (string) : Password value
            description (string) : Argument description, only seen if manually
                                   launching the template
        """
        parameter =  {
            "Description" : description,
            "Type": "String",
            "NoEcho": "true"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)

    @staticmethod
    def IP(key, value, description=""):
        """Create a String argument that checks the value to make sure it is in
        a valid IPv4 format.

        Note: Valid IPv4 format is x.x.x.x through xxx.xxx.xxx.xxx, the actual
              subnet number is not checked to make sure it is between 0 and 255

        Args:
            key (string) : Unique name associated with the argument
            value (string) : IPv4 value
            description (string) : Argument description, only seen if manually
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
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)

    @staticmethod
    def Port(key, value, description=""):
        """Create a Number argument that checks the value to make sure it is a
        valid port number.

        Args:
            key (string) : Unique name associated with the argument
            value (string|int) : Port value
            description (string) : Argument description, only seen if manually
                                   launching the template
        """
        parameter =  {
            "Description" : description,
            "Type": "Number",
            "MinValue": "1",
            "MaxValue": "65535"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)

    @staticmethod
    def CIDR(key, value, description=""):
        """Create a String argument that checks the value to make sure it is in
        a valid IPv4 CIDR format.

        Note: Valid IPv4 CIDR format is x.x.x.x/x through xxx.xxx.xxx.xxx/xx, the
              actual subnet number is not checked to make sure it is between 0
              and 255 and the CIDR mask is not checked to make sure its is between
              1 and 32

        Args:
            key (string) : Unique name associated with the argument
            value (string) : IPv4 CIDR value
            description (string) : Argument description, only seen if manually
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
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)

    @staticmethod
    def VPC(key, value, description=""):
        """Create a VPC ID argument that makes sure the value is a valid VPC ID.

        Args:
            key (string) : Unique name associated with the argument
            value (string) : VPC ID value
            description (string) : Argument description, only seen if manually
                                   launching the template
        """
        parameter = {
            "Description" : description,
            "Type": "AWS::EC2::VPC::Id"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)

    @staticmethod
    def Subnet(key, value, description=""):
        """Create an (AWS) Subnet ID argument that makes sure the value is a
        valid Subnet ID.

        Args:
            key (string) : Unique name associated with the argument
            value (string) : Subnet ID value
            description (string) : Argument description, only seen if manually
                                   launching the template
        """
        parameter = {
            "Description" : description,
            "Type": "AWS::EC2::Subnet::Id"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)

    @staticmethod
    def AMI(key, value, description=""):
        """Create a AMI ID argument that makes sure the value is a valid AMI ID.

        Args:
            key (string) : Unique name associated with the argument
            value (string) : AMI ID value
            description (string) : Argument description, only seen if manually
                                   launching the template
        """
        parameter = {
            "Description" : description,
            "Type": "AWS::EC2::Image::Id"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)

    @staticmethod
    def Instance(key, value, description=""):
        """Create a Instance ID argument that makes sure the value is a valid Instance ID.

        Args:
            key (string) : Unique name associated with the argument
            value (string) : Instance ID value
            description (string) : Argument description, only seen if manually
                                   launching the template
        """
        parameter = {
            "Description" : description,
            "Type": "AWS::EC2::Instance::Id"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)

    @staticmethod
    def KeyPair(key, value, hostname):
        """Create a KeyPair KeyName argument that makes sure the value is a
        valid KeyPair name.

        Args:
            key (string) : Unique name associated with the argument
            value (string) : Key Pair value
            description (string) : Argument description, only seen if manually
                                   launching the template
        """
        parameter = {
            "Description" : "Name of an existing EC2 KeyPair to enable SSH access to '{}'".format(hostname),
            "Type": "AWS::EC2::KeyPair::KeyName",
            "ConstraintDescription" : "must be the name of an existing EC2 KeyPair."
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)

    @staticmethod
    def SecurityGroup(key, value, description=""):
        """Create a SecurityGroup ID argument that makes sure the value is a
        valid SecurityGroup ID.

        Args:
            key (string) : Unique name associated with the argument
            value (string) : Security Group ID value
            description (string) : Argument description, only seen if manually
                                   launching the template
        """
        parameter = {
            "Description" : description,
            "Type": "AWS::EC2::SecurityGroup::Id"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)

    @staticmethod
    def RouteTable(key, value, description=""):
        """Create a RouteTable ID argument.

        NOTE: AWS does not currently recognize AWS::EC2::RouteTable::Id as a
              valid argument type. Therefore this argument is a String
              argument.

        Args:
            key (string) : Unique name associated with the argument
            value (string) : Route Table ID value
            description (string) : Argument description, only seen if manually
                                   launching the template
        """
        parameter = {
            "Description" : description,
            "Type" : "For whatever reason CloudFormation does not recognize RouteTable::Id",
            "Type" : "AWS::EC2::RouteTable::Id",
            "Type" : "String"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)

    @staticmethod
    def Certificate(key, value, description=""):
        """Create a Certificate ID argument that makes sure the value is a
        valid Certificate ID.

        Args:
            key (string) : Unique name associated with the argument
            value (string) : Certificate ID value
            description (string) : Argument description, only seen if manually
                                   launching the template
        """
        parameter = {
            "Description" : description,
            "Type": "AWS::ACM::Certificate::Id"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)

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

    # TODO DP: figure out if we can extract the region from the session used to
    #          create the stack and use a template argument
    def __init__(self, domain, region = "us-east-1"):
        """CloudFormationConfiguration constructor

        A domain name is in either <vpc>.<tld> or <subnet>.<vpc>.<tld> format and
        is validated by hosts.py to determine the IP subnets.

        Note: region is used when creating the Hosted Zone for a new VPC.

        Args:
            domain (string) : Domain that the CloudFormation template will work in.
            region (string) : AWS region that the configuration will be created in.
        """
        self.resources = {}
        self.parameters = {}
        self.arguments = []
        self.region = region
        self.keypairs = {}

        dots = len(domain.split("."))
        if dots == 2: # vpc.tld
            self.vpc_domain = domain
            self.vpc_subnet = hosts.lookup(domain)
            self.subnet_domain = None
            self.subnet_subnet = None
        elif dots == 3: # subnet.vpc.tld
            self.vpc_domain = domain.split(".", 1)[1]
            self.vpc_subnet = hosts.lookup(self.vpc_domain)
            self.subnet_domain = domain
            self.subnet_subnet = hosts.lookup(domain)
        else:
            raise Exception("Not a valiid VPC or Subnet domain name")

    def _create_template(self, description=""):
        """Create the JSON CloudFormation template from the resources that have
        be added to the object.

        Args:
            description (string) : Template description

        Returns:
            (string) : The JSON formatted CloudFormation template
        """
        return json.dumps({"AWSTemplateFormatVersion" : "2010-09-09",
                           "Description" : description,
                           "Parameters": self.parameters,
                           "Resources": self.resources})

    def generate(self, name, folder):
        """Generate the CloudFormation template and arguments files

        Args:
            name (string) : Name to give the .template and .arguments files
            folder (string) : Folder to save the files under
        """
        with open(os.path.join(folder, name + ".template"), "w") as fh:
            fh.write(self._create_template())

        with open(os.path.join(folder, name + ".arguments"), "w") as fh:
            json.dump(self.arguments, fh, indent=4)

    def create(self, session, name, wait = True):
        """Launch the template this object represents in CloudFormation.

        Args:
            session (Session) : Boto3 session used to launch the configuration
            name (string) : Name of the CloudFormation Stack
            wait (bool) : If True, wait for the stack to be created, printing
                          status information

        Returns:
            (bool|None) : If wait is True, the result of launching the stack,
                          else None
        """
        for argument in self.arguments:
            if argument["ParameterValue"] is None:
                raise Exception("Could not determine argument '{}'".format(argument["ParameterKey"]))

        client = session.client('cloudformation')
        response = client.create_stack(
            StackName = name,
            TemplateBody = self._create_template(),
            Parameters = self.arguments,
            Tags = [
                {"Key": "Commit", "Value": lib.get_commit()}
            ]
        )

        rtn = None
        if wait:
            get_status = lambda r: r['Stacks'][0]['StackStatus']
            response = client.describe_stacks(StackName=name)
            if len(response['Stacks']) == 0:
                print("Problem launching stack")
            else:
                print("Waiting for create ", end="", flush=True)
                while get_status(response) == 'CREATE_IN_PROGRESS':
                    time.sleep(5)
                    print(".", end="", flush=True)
                    response = client.describe_stacks(StackName=name)
                print(" done")

                if get_status(response) == 'CREATE_COMPLETE':
                    print("Created stack '{}'".format(name))
                    rtn = True
                else:
                    print("Status of stack '{}' is '{}'".format(name, get_status(response)))
                    rtn = False
        return rtn

    def add_arg(self, arg):
        """Add an Arg class instance to the internal configuration.

        Args:
            arg (Arg) : Arg instance to add to the template
        """
        if arg.key not in self.parameters:
            self.parameters[arg.key] = arg.parameter
            self.arguments.append(arg.argument)

    def add_vpc(self, key="VPC"):
        """Add a VPC to the configuration.

        VPC name is derived from the domain given to the constructor.

        Args:
            key (string) : Unique name for the resource in the template
        """
        self.resources[key] = {
            "Type" : "AWS::EC2::VPC",
            "Properties" : {
                "CidrBlock" : { "Ref" : key + "Subnet" },
                "EnableDnsSupport" : "true",
                "EnableDnsHostnames" : "true",
                "Tags" : [
                    {"Key" : "Stack", "Value" : { "Ref" : "AWS::StackName"} },
                    {"Key" : "Name", "Value" : { "Ref" : key + "Domain"} }
                ]
            }
        }

        self.resources["DNSZone"] = {
            "Type" : "AWS::Route53::HostedZone",
            "Properties" : {
                "HostedZoneConfig" : {
                    "Comment": "Internal DNS Zone for the VPC of {}".format(self.vpc_domain)
                },
                "Name" : { "Ref" : key + "Domain" },
                "VPCs" : [ {
                    "VPCId": { "Ref" : key },
                    "VPCRegion": { "Ref" : key + "Region" }
                }]
            }
        }

        subnet = Arg.CIDR(key + "Subnet", self.vpc_subnet,
                          "Subnet of the VPC '{}'".format(key))
        self.add_arg(subnet)

        domain = Arg.String(key + "Domain", self.vpc_domain,
                            "Domain of the VPC '{}'".format(key))
        self.add_arg(domain)

        region_ = Arg.String(key + "Region", self.region,
                            "Region of the VPC '{}'".format(key))
        self.add_arg(region_)

    def add_subnet(self, key="Subnet", vpc="VPC", az=None):
        """Add a Subnet to the configuration.

        Subnet name is derived from the domain given to the constructor.

        Args:
            key (string) : Unique name for the resource in the template
            vpc (string) : Unique argument key for the VPC the subnet will be created in
            az (string|None) : Availability Zone to launch the subnet in or None
                               to allow AWS to decide
        """
        self.resources[key] = {
            "Type" : "AWS::EC2::Subnet",
            "Properties" : {
                "VpcId" : { "Ref" : vpc },
                "CidrBlock" : { "Ref" : key + "Subnet" },
                "Tags" : [
                    {"Key" : "Stack", "Value" : { "Ref" : "AWS::StackName"} },
                    {"Key" : "Name", "Value" : { "Ref" : key + "Domain" } }
                ]
            }
        }

        if az is not None:
            self.resources[key]["Properties"]["AvailabilityZone"] = az

        subnet = Arg.CIDR(key + "Subnet", self.subnet_subnet,
                          "Subnet of the Subnet '{}'".format(key))
        self.add_arg(subnet)
        domain = Arg.String(key + "Domain", self.subnet_domain,
                            "Domain of the Subnet '{}'".format(key))
        self.add_arg(domain)

    def add_all_azs(self, session):
        """Add Internal and External subnets for each availability zone.

        For each availability zone in the connected region, create an Internal
        and External subnets so that AWS resources like AutoScale Groups can
        run across all zones within the region.

        Args:
            session (Session) : Boto3 session used to lookup availability zones

        Returns:
            (tuple) : Tuple of two lists (internal, external) that contain the
                      template argument names for each of the added subnets
        """
        internal = []
        external = []
        for az, sub in lib.azs_lookup(session):
            name = sub.capitalize() + "InternalSubnet"
            self.subnet_domain = sub + "-internal." + self.vpc_domain
            self.subnet_subnet = hosts.lookup(self.subnet_domain)
            self.add_subnet(name, az = az)
            internal.append(name)

            name = sub.capitalize() + "ExternalSubnet"
            self.subnet_domain = sub + "-external." + self.vpc_domain
            self.subnet_subnet = hosts.lookup(self.subnet_domain)
            self.add_subnet(name, az = az)
            external.append(name)

        return (internal, external)

    def find_all_availability_zones(self, session):
        """Add template arguments for each internal/external availability zone subnet.

        A companion method to add_all_azs(), that will add to the current template
        configuration arguments for each internal and external subnet that exist
        in the current region.

        Args:
            session (Session) : Boto3 session used to lookup availability zones

        Returns:
            (tuple) : Tuple of two lists (internal, external) that contain the
                      template argument names for each of the added subnet arguments
        """
        internal = []
        external = []

        for az, sub in lib.azs_lookup(session):
            name = sub.capitalize() + "InternalSubnet"
            domain = sub + "-internal." + self.vpc_domain
            id = lib.subnet_id_lookup(session, domain)
            self.add_arg(Arg.Subnet(name, id))
            internal.append(name)

            name = sub.capitalize() + "ExternalSubnet"
            domain = sub + "-external." + self.vpc_domain
            id = lib.subnet_id_lookup(session, domain)
            self.add_arg(Arg.Subnet(name, id))
            external.append(name)

        return (internal, external)

    def add_ec2_instance(self, key, hostname, ami, keypair, subnet="Subnet", type_="t2.micro", iface_check=True, public_ip=False, security_groups=None, user_data=None, meta_data=None, depends_on=None):
        """Add an EC2 instance to the configuration

        Args:
            key (string) : Unique name for the resource in the template
            hostname (string) : The hostname / instance name of the instance
            ami (string) : The AMI ID of the image to base the instance on
            subnet (string) : The Subnet unique name within the configuration to launch this machine in
            type_ (string) : The instance type to create
            iface_check (bool) : Should the network check if the traffic is destined for itself
                                 (usedful for NAT instances)
            public_ip (bool) : Should the instance gets a public IP address
            security_groups (None|list) : A list of SecurityGroup unique names within the configuration
            user_data (None|string) : A string of user-data to give to the instance when launching
            meta_data (None|dict) : A dictionary of meta-data to include with the configuration
            depends_on (None|string|list): A unique name or list of unique names of resources within the
                                           configuration and is used to determine the launch order of resources
        """
        self.resources[key] = {
            "Type" : "AWS::EC2::Instance",
            "Properties" : {
                "ImageId" : { "Ref" : key + "AMI" },
                "InstanceType" : get_scenario(type_, "t2.micro"),
                "KeyName" : { "Ref" : key + "Key" },
                "SourceDestCheck": bool_str(iface_check),
                "Tags" : [
                    {"Key" : "Stack", "Value" : { "Ref" : "AWS::StackName"} },
                    {"Key" : "Name", "Value" : { "Ref": key + "Hostname" } }
                ],
                "NetworkInterfaces" : [{
                    "AssociatePublicIpAddress" : bool_str(public_ip),
                    "DeviceIndex"              : "0",
                    "DeleteOnTermination"      : "true",
                    "SubnetId"                 : { "Ref" : subnet },
                }]
            }
        }

        if type(ami) == tuple:
            commit = ami[1]
            ami = ami[0]

            if commit is not None:
                kv = {"Key": "AMI Commit", "Value": commit}
                self.resources[key]["Properties"]["Tags"].append(kv)

        if depends_on is not None:
            self.resources[key]["DependsOn"] = depends_on

        if security_groups is not None:
            sgs = []
            for sg in security_groups:
                sgs.append({ "Ref" : sg })
            self.resources[key]["Properties"]["NetworkInterfaces"][0]["GroupSet"] = sgs

        if meta_data is not None:
            self.resources[key]["Metadata"] = meta_data

        if user_data is not None:
            self.resources[key]["Properties"]["UserData"] = { "Fn::Base64" : user_data }

        _ami = Arg.AMI(key + "AMI", ami,
                       "AMI for the EC2 Instance '{}'".format(key))
        self.add_arg(_ami)

        _key = Arg.KeyPair(key + "Key", keypair, hostname)
        self.add_arg(_key)
        self.keypairs[hostname] = keypair

        _hostname = Arg.String(key + "Hostname", hostname,
                               "Hostname of the EC2 Instance '{}'".format(key))
        self.add_arg(_hostname)

        self._add_record_cname(key, hostname, ec2 = True)

    def add_rds_db(self, key, hostname, port, db_name, username, password, subnets, type_="db.t2.micro", storage="5", security_groups=None):
        """Add an RDS DB instance to the configuration

        Args:
            key (string) : Unique name for the resource in the template
            hostname (string) : The hostname / instance name of the RDS DB
            port (int) : The port for the DB instance to listen on
            db_name (string) : The name of the database to create on the DB instance
            username (string) : The master username for the database
            password (string) : The (plaintext) password for the master username
            subnets (list) : A list of Subnet unique names within the configuration across which
                             to create a DB SubnetGroup for the DB Instance to launch into
            type_ (string) : The RDS instance type to create
            storage (int|string) : The storage size of the database (in GB)
            security_groups (None|list) : A list of SecurityGroup unique names within the configuration
        """
        scenario = os.environ["SCENARIO"]
        multi_az = {
            "development": "false",
            "production": "true",
        }.get(scenario, "false")

        self.resources[key] = {
            "Type" : "AWS::RDS::DBInstance",

            "Properties" : {
                "Engine" : "mysql",
                "LicenseModel" : "general-public-license",
                "EngineVersion" : "5.6.23",
                "DBInstanceClass" : get_scenario(type_, "db.t2.micro"),
                "MultiAZ" : multi_az,
                "StorageType" : "standard",
                "AllocatedStorage" : str(storage),
                "DBInstanceIdentifier" : { "Ref" : key + "Hostname" },
                "MasterUsername" : { "Ref" : key + "Username" },
                "MasterUserPassword" : { "Ref" : key + "Password" },
                "DBSubnetGroupName" : { "Ref" : key + "SubnetGroup" },
                "PubliclyAccessible" : "false",
                "DBName" : { "Ref" : key + "DBName" },
                "Port" : { "Ref" : key + "Port" },
                "StorageEncrypted" : "false"
            }
        }

        self.resources[key + "SubnetGroup"] = {
            "Type" : "AWS::RDS::DBSubnetGroup",
            "Properties" : {
                "DBSubnetGroupDescription" : { "Ref" : key + "Hostname" },
                "SubnetIds" : [{ "Ref" : subnet } for subnet in subnets]
            }
        }

        if security_groups is not None:
            sgs = []
            for sg in security_groups:
                sgs.append({ "Ref" : sg })
            self.resources[key]["Properties"]["VPCSecurityGroups"] = sgs

        hostname_ = Arg.String(key + "Hostname", hostname.replace('.','-'),
                               "Hostname of the RDS DB Instance '{}'".format(key))
        self.add_arg(hostname_)

        port_ = Arg.Port(key + "Port", port,
                         "DB Server Port for the RDS DB Instance '{}'".format(key))
        self.add_arg(port_)

        name_ = Arg.String(key + "DBName", db_name,
                           "Name of the intial database on the RDS DB Instance '{}'".format(key))
        self.add_arg(name_)

        username_ = Arg.String(key + "Username", username,
                               "Master Username for RDS DB Instance '{}'".format(key))
        self.add_arg(username_)

        password_ = Arg.Password(key + "Password", password,
                                 "Master User Password for RDS DB Instance '{}'".format(key))
        self.add_arg(password_)

        self._add_record_cname(key, hostname, rds = True)

    def add_dynamo_table_from_json(self, key, name, KeySchema, AttributeDefinitions, ProvisionedThroughput):
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
            key (string) : Unique name (within the configuration) for this instance
            name (string) : DynamoDB Table name to create
            KeySchema (list) : List of dict of AttributeName / KeyType
            AttributeDefinitions (list) : List of dict of AttributeName / AttributeType
            ProvisionedThroughput (dictionary) : Dictionary of ReadCapacityUnits / WriteCapacityUnits
        """

        props = {
            "TableName" : { "Ref" : key + "TableName" },
            "KeySchema" : KeySchema,
            "AttributeDefinitions" : AttributeDefinitions,
            "ProvisionedThroughput" : ProvisionedThroughput
        }

        self.resources[key] = {
            "Type" : "AWS::DynamoDB::Table",
            "Properties" : props
        }

        table_name = Arg.String(
            key + "TableName", name,
            "Name of the DynamoDB table created by instance '{}'".format(key))

        self.add_arg(table_name)

    def add_dynamo_table(self, key, name, attributes, key_schema, throughput):
        """Add an DynamoDB Table to the configuration

        Args:
            key (string) : Unique name (within the configuration) for this instance
            name (string) : DynamoDB Table name to create
            attributes (dict) : Dictionary of {'AttributeName' : 'AttributeType', ...}
            key_schema (dict) : Dictionary of {'AttributeName' : 'KeyType', ...}
            throughput (tuple) : Tuple of (ReadCapacity, WriteCapacity)
                                 ReadCapacity is the minimum number of consistent reads of items per second
                                              before Amazon DynamoDB balances the loads
                                 WriteCapacity is the minimum number of consistent writes of items per second
                                               before Amazon DynamoDB balances the loads
        """
        attr_defs = []
        for key_ in attributes:
            attr_defs.append({"AttributeName": key_, "AttributeType": attributes[key_]})

        key_schema_ = []
        for key_ in key_schema:
            key_schema_.append({"AttributeName": key_, "KeyType": key_schema[key_]})

        self.resources[key] = {
            "Type" : "AWS::DynamoDB::Table",
            "Properties" : {
                "TableName" : { "Ref" : key + "TableName" },
                "AttributeDefinitions" : attr_defs,
                "KeySchema" : key_schema_,
                "ProvisionedThroughput" : {
                    "ReadCapacityUnits" : int(throughput[0]),
                    "WriteCapacityUnits" : int(throughput[1])
                }
            }
        }

        table_name = Arg.String(key + "TableName", name,
                                "Name of the DynamoDB table created by instance '{}'".format(key))
        self.add_arg(table_name)

    def add_redis_cluster(self, key, hostname, subnets, security_groups, type_="cache.t2.micro", port=6379, version="2.8.24"):
        """Add a Redis ElastiCache cluster to the configuration

            Note: Redis ElastiCache clusters are limited to 1 node. For a multi- node
                  cluster using ElastiCache use the add_redis_replication() method.

        Args:
            key (string) : Unique name for the resource in the template
            hostname (string) : The hostname / instance name of the Redis Cache
            subnets (list) : A list of Subnet unique names within the configuration across which
                             to create a DB SubnetGroup for the DB Instance to launch into
            security_groups (list) : A list of SecurityGroup unique names within the configuration
            type_ (string) : The ElastiCache instance type to create
            port (int) : The port for the Redis instance to listen on
            version (string) : Redis version to run on the instance
        """
        self.resources[key] =  {
            "Type" : "AWS::ElastiCache::CacheCluster",
            "Properties" : {
                #"AutoMinorVersionUpgrade" : "false", # defaults to true - Indicates that minor engine upgrades will be applied automatically to the cache cluster during the maintenance window.
                "CacheNodeType" : get_scenario(type_, "cache.t2.micro"),
                "CacheSubnetGroupName" : { "Ref" : key + "SubnetGroup" },
                "Engine" : "redis",
                "EngineVersion" : version,
                "NumCacheNodes" : "1",
                "Port" : port,
                #"PreferredMaintenanceWindow" : String, # don't know the default - site says minimum 60 minutes, infrequent and announced on AWS forum 2w prior
                "Tags" : [
                    {"Key" : "Stack", "Value" : { "Ref" : "AWS::StackName"} },
                    {"Key" : "Name", "Value" : { "Ref": key + "Hostname" } }
                ],
                "VpcSecurityGroupIds" :  [{ "Ref" : sg } for sg in security_groups]
            },
            "DependsOn" : key + "SubnetGroup"
        }

        self.resources[key + "SubnetGroup"] = {
            "Type" : "AWS::ElastiCache::SubnetGroup",
            "Properties" : {
                "Description" : { "Ref" : key + "Hostname" },
                "SubnetIds" : [{ "Ref" : subnet } for subnet in subnets]
            }
        }

        hostname_ = Arg.String(key + "Hostname", hostname.replace('.','-'),
                               "Hostname of the Redis Cluster '{}'".format(key))
        self.add_arg(hostname_)

        self._add_record_cname(key, hostname, cluster = True)

    def add_redis_replication(self, key, hostname, subnets, security_groups, type_="cache.m3.medium", port=6379, version="2.8.24", clusters=1):
        """Add a Redis ElastiCache Replication Group to the configuration

        Args:
            key (string) : Unique name for the resource in the template
            hostname (string) : The hostname / instance name of the Redis Cache
            subnets (list) : A list of Subnet unique names within the configuration across which
                             to create a DB SubnetGroup for the DB Instance to launch into
            security_groups (list) : A list of SecurityGroup unique names within the configuration
            type_ (string) : The ElastiCache instance type to create
            port (int|string) : The port for the Redis instance to listen on
            version (string) : Redis version to run on the instance
            clusters (int|string) : Number of cluster instances to create (1 - 5)
        """
        clusters = int(get_scenario(clusters, 1))
        self.resources[key] =  {
            "Type" : "AWS::ElastiCache::ReplicationGroup",
            "Properties" : {
                "AutomaticFailoverEnabled" : bool_str(clusters > 1),
                #"AutoMinorVersionUpgrade" : "false", # defaults to true - Indicates that minor engine upgrades will be applied automatically to the cache cluster during the maintenance window.
                "CacheNodeType" : get_scenario(type_, "cache.m3.medium"),
                "CacheSubnetGroupName" : { "Ref" : key + "SubnetGroup" },
                "Engine" : "redis",
                "EngineVersion" : version,
                "NumCacheClusters" : clusters,
                "Port" : int(port),
                #"PreferredCacheClusterAZs" : [ String, ... ],
                #"PreferredMaintenanceWindow" : String, # don't know the default - site says minimum 60 minutes, infrequent and announced on AWS forum 2w prior
                "ReplicationGroupDescription" : { "Ref" : key + "Hostname" },
                "SecurityGroupIds" : [{ "Ref" : sg } for sg in security_groups]
            },
            "DependsOn" : key + "SubnetGroup"
        }

        self.resources[key + "SubnetGroup"] = {
            "Type" : "AWS::ElastiCache::SubnetGroup",
            "Properties" : {
                "Description" : { "Ref" : key + "Hostname" },
                "SubnetIds" : [{ "Ref" : subnet } for subnet in subnets]
            }
        }

        hostname_ = Arg.String(key + "Hostname", hostname.replace('.','-'),
                               "Hostname of the Redis Cluster '{}'".format(key))
        self.add_arg(hostname_)

        self._add_record_cname(key, hostname, replication = True)

    def add_security_group(self, key, name, rules, vpc="VPC"):
        """Add SecurityGroup to the configuration

        Args:
            key (string) : Unique name for the resource in the template
            name (string) : The name to give the SecurityGroup
                            The name is appended with the configuration's VPC domain name
            rules (list) : A list of tuples (protocol, from port, to port, cidr)
                           Where protocol/from/to can be -1 if open access is desired
            vpc (string) : The VPC unique name within the configuration to add the Security Group to
        """
        ports = "/".join(map(lambda x: x[1] + "-" + x[2], rules))
        ingress = []
        for rule in rules:
            ingress.append({"IpProtocol" : rule[0], "FromPort" : rule[1], "ToPort" : rule[2], "CidrIp" : rule[3]})

        self.resources[key] = {
          "Type" : "AWS::EC2::SecurityGroup",
          "Properties" : {
            "VpcId" : { "Ref" : vpc },
            "GroupDescription" : "Enable access to ports {}".format(ports),
            "SecurityGroupIngress" : ingress,
             "Tags" : [
                {"Key" : "Stack", "Value" : { "Ref" : "AWS::StackName"} },
                {"Key" : "Name", "Value" : { "Fn::Join" : [ ".", [name, { "Ref" : vpc + "Domain" }]]}}
            ]
          }
        }

        domain = Arg.String(vpc + "Domain", self.vpc_domain,
                            "Domain of the VPC '{}'".format(vpc))
        self.add_arg(domain)

    def add_route_table(self, key, name, vpc="VPC", subnets=["Subnet"]):
        """Add RouteTable to the configuration

        Args:
            key (string) : Unique name for the resource in the template
            name (string) : The name to give the RouteTable
                            The name is appended with the configuration's VPC domain name
            vpc (string) : The VPC unique name within the configuration to add the RouteTable to
            subnets (list) : A list of Subnet unique names within the configuration to attach the RouteTable to
        """
        self.resources[key] = {
          "Type" : "AWS::EC2::RouteTable",
          "Properties" : {
            "VpcId" : {"Ref" : vpc},
            "Tags" : [
                {"Key" : "Stack", "Value" : { "Ref" : "AWS::StackName"} },
                {"Key" : "Name", "Value" : { "Fn::Join" : [ ".", [name, { "Ref" : vpc + "Domain" }]]}}
            ]
          }
        }

        domain = Arg.String(vpc + "Domain", self.vpc_domain,
                            "Domain of the VPC '{}'".format(vpc))
        self.add_arg(domain)

        for subnet in subnets:
            key_ = key + "SubnetAssociation" + str(subnets.index(subnet))
            self.add_route_table_association(key_, key, subnet)

    def add_route_table_association(self, key, route_table, subnet="Subnet"):
        """Add SubnetRouteTableAssociation to the configuration

        Args:
            key (string) : Unique name for the resource in the template
            route_table (string) : The unique name of the RouteTable in the configuration
            subnet (string) : The the unique name of the Subnet to associate the RouteTable with
        """
        self.resources[key] = {
          "Type" : "AWS::EC2::SubnetRouteTableAssociation",
          "Properties" : {
            "SubnetId" : { "Ref" : subnet },
            "RouteTableId" : { "Ref" : route_table }
          }
        }

    def add_route_table_route(self, key, route_table, cidr="0.0.0.0/0", gateway=None, peer=None, instance=None, depends_on=None):
        """Add a Route to the configuration

        Note: Only one of gateway/peer/instance should be specified for a call

        Args:
            key (string) : Unique name for the resource in the template
            route_table (string) : The unique name of the RouteTable to add the Route to
            cidr (string) : A CIDR formatted (x.x.x.x/y) subnet of the route
            gateway (None|string) The unique name of the target InternetGateway
            peer (None|string) : The unique name of the target VPCPeerConnection
            instance (None|string) : The unique name of the target EC2 Instance
            depends_on (None|string|list): A unique name or list of unique names of resources within the
                                           configuration and is used to determine the launch order of resources
        """
        self.resources[key] = {
          "Type" : "AWS::EC2::Route",
          "Properties" : {
            "RouteTableId" : { "Ref" : route_table },
            "DestinationCidrBlock" : { "Ref" : key + "Cidr" },
          }
        }

        checks = [gateway, peer, instance]
        check = checks.count(None)
        if len(checks) - checks.count(None) != 1:
            raise Exception("Required to specify one and only one of the following arguments: gateway|peer|instance")


        if gateway is not None:
            self.resources[key]["Properties"]["GatewayId"] = { "Ref" : gateway }
        if peer is not None:
            self.resources[key]["Properties"]["VpcPeeringConnectionId"] = { "Ref" : peer }
        if instance is not None:
            self.resources[key]["Properties"]["InstanceId"] = { "Ref" : instance }

        if depends_on is not None:
            self.resources[key]["DependsOn"] = depends_on

        cidr = Arg.CIDR(key + "Cidr", cidr,
                        "Destination CIDR Block for Route '{}'".format(key))
        self.add_arg(cidr)

    def add_internet_gateway(self, key, name="internet", vpc="VPC"):
        """Add an InternetGateway to the configuration

        Args:
            key (string) : Unique name for the resource in the template
            name (string) : The name to give the InternetGateway
                            The name is appended with the configuration's VPC domain name
            vpc (string) : The VPC unique name within the configuration to add the InternetGateway to
        """
        self.resources[key] = {
          "Type" : "AWS::EC2::InternetGateway",
          "Properties" : {
            "Tags" : [
                {"Key" : "Stack", "Value" : { "Ref" : "AWS::StackName"} },
                {"Key" : "Name", "Value" : { "Fn::Join" : [ ".", [name, { "Ref" : vpc + "Domain" }]]}}
            ]
          },
          "DependsOn" : vpc
        }

        self.resources["Attach" + key] = {
           "Type" : "AWS::EC2::VPCGatewayAttachment",
           "Properties" : {
             "VpcId" : { "Ref" : vpc },
             "InternetGatewayId" : { "Ref" : key }
           },
           "DependsOn" : key
        }

        domain = Arg.String(vpc + "Domain", self.vpc_domain,
                            "Domain of the VPC '{}'".format(vpc))
        self.add_arg(domain)

    def add_vpc_peering(self, key, vpc, peer_vpc):
        """Add a VPCPeeringConnection to the configuration

        Args:
            key (string) : Unique name for the resource in the template
            vpc (string) : The VPC unique name within the configuration to create the peering connection from
            peer_vpc (string) : The VPC unique name within the configuration to create the peering connection to
        """
        self.resources[key] = {
            "Type" : "AWS::EC2::VPCPeeringConnection",
            "Properties" : {
                "VpcId" : { "Ref" : key + "VPC" },
                "PeerVpcId" : { "Ref" : key + "PeerVPC" },
                "Tags" : [
                    {"Key" : "Stack", "Value" : { "Ref" : "AWS::StackName"} }
                ]
            }
        }

        vpc_ = Arg.VPC(key + "VPC", vpc,
                       "Originating VPC for the peering connection")
        self.add_arg(vpc_)

        peer_vpc_ = Arg.VPC(key + "PeerVPC", peer_vpc,
                            "Destination VPC for the peering connection")
        self.add_arg(peer_vpc_)

    def add_loadbalancer(self, key, name, listeners, instances=None, subnets=None, security_groups=None,
                         healthcheck_target="HTTP:80/ping/", public=True, depends_on=None ):
        """
        Add LoadBalancer to the configuration

        Args:
            key (string) : Unique name for the resource in the template
            name (string) : The name to give this elb
            listeners (list) : A list of tuples for the elb
                               (elb_port, instance_port, protocol [, ssl_cert_id])
                                   elb_port (string) : The port for the elb to listening on
                                   instance_port (string) : The port on the instance that the elb sends traffic to
                                   protocol (string) : The protocol used, ex: HTTP, HTTPS
                                   ssl_cert_id (Optional string) : The AWS ID of the SSL cert to use
            instances (None|list) : A list of Instance unique names within the configuration to attach to the LoadBalancer
            subnets (None|list) : A list of Subnet unique names within the configuration to attach the LoadBalancer to
            security_groups (None|list) : A list of SecurityGroup unique names within the configuration to apply to the LoadBalancer
            healthcheck_target (string) : The URL used for for health checks Ex: "HTTP:80/"
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
                    "UnhealthyThreshold": "2",
                    "Interval": "30",
                    "Timeout": "5"
                },
                "LBCookieStickinessPolicy" : [{"PolicyName": key + "Policy"}],
                "LoadBalancerName": name.replace(".", "-"),  #elb names can't have periods in them
                "Listeners": listener_defs,
                "Scheme": "internet-facing" if public else "internal",
                "Tags": [
                    {"Key": "Stack", "Value": { "Ref": "AWS::StackName"}}
                ]
            }
        }

        if instances is not None:
            instance_refs = [{ "Ref" : ref } for ref in instances]
            self.resources[key]["Properties"]["Instances"] = instance_refs
        if security_groups is not None:
            sgs = [{"Ref": sg } for sg in security_groups]
            self.resources[key]["Properties"]["SecurityGroups"] = sgs
        if subnets is not None:
            ref_subs = [{"Ref": sub } for sub in subnets]
            self.resources[key]["Properties"]["Subnets"] = ref_subs
        if depends_on is not None:
            self.resources[key]["DependsOn"] = depends_on

        # self.resources["Outputs"] = {
        #     "URL" : {
        #         "Description": "URL of the ELB website",
        #         "Value":  { "Fn::Join": ["", ["http://", {"Fn::GetAtt": [ "ElasticLoadBalancer", "DNSName"]}]]}
        #     }
        # }

        self._add_record_cname(key, name, elb = True)

    def add_autoscale_group(self, key, hostname, ami, keypair, subnets=["Subnet"], type_="t2.micro", public_ip=False, security_groups=[], user_data=None, min=1, max=1, elb=None, notifications=None, role=None, depends_on=None):
        """Add an AutoScalingGroup to the configuration

        Args:
            key (string) : Unique name for the resource in the template
            hostname (string) : The hostname / instance name of the instances
            ami (string) : The AMI ID of the image to base the instances on
            subnets (list) : A list of Subnet unique names within the configuration to launch the instances in
            type_ (string) : The instance type to create
            public_ip (bool) : Should the instances gets public IP addresses
            security_groups (list) : A list of SecurityGroup unique names within the configuration to apply to the instances
            user_data (None|string) : A string of user-data to give to the instance when launching
            min (int|string) : The minimimum number of instances in the AutoScalingGroup
            max (int|string) : The maximum number of instances in the AutoScalingGroup
            elb (None|string) : The unique name of a LoadBalancer within the configuration to attach the AutoScalingGroup to
            depends_on (None|string|list): A unique name or list of unique names of resources within the
                                           configuration and is used to determine the launch order of resources
        """
        self.resources[key] = {
            "Type" : "AWS::AutoScaling::AutoScalingGroup",
            "Properties" : {
                #"DesiredCapacity" : get_scenario(min, 1), Initial capacity, will min size also ensure the size on startup?
                "HealthCheckType" : "EC2" if elb is None else "ELB",
                "HealthCheckGracePeriod" : 30, # seconds
                "LaunchConfigurationName" : { "Ref": key + "Configuration" },
                "LoadBalancerNames" : [] if elb is None else [{ "Ref": elb }],
                "MaxSize" : str(get_scenario(max, 1)),
                "MinSize" : str(get_scenario(min, 1)),
                "Tags" : [
                    {"Key" : "Stack", "Value" : { "Ref" : "AWS::StackName"}, "PropagateAtLaunch": "true" },
                    {"Key" : "Name", "Value" : { "Ref": key + "Hostname" }, "PropagateAtLaunch": "true" }
                ],
                "VPCZoneIdentifier" : [{ "Ref" : subnet } for subnet in subnets]
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
                    "TopicARN" : {"Ref": topic}
                } for topic in notifications
            ]

        if depends_on is not None:
            self.resources[key]["DependsOn"] = depends_on

        self.resources[key + "Configuration"] = {
            "Type" : "AWS::AutoScaling::LaunchConfiguration",
            "Properties" : {
                "AssociatePublicIpAddress" : public_ip,
                #"EbsOptimized" : Boolean, EBS I/O optimized
                "ImageId" : { "Ref" : key + "AMI" },
                "InstanceMonitoring" : False, # CloudWatch Monitoring...
                "InstanceType" : get_scenario(type_, "t2.micro"),
                "KeyName" : { "Ref" : key + "Key" },
                "SecurityGroups" : [{ "Ref" : sg } for sg in security_groups],
                "UserData" : "" if user_data is None else { "Fn::Base64" : user_data }
            }
        }

        if role is not None:
            self.resources[key + "Configuration"]["Properties"]["IamInstanceProfile"] = role

        if type(ami) == tuple:
            commit = ami[1]
            ami = ami[0]

            if commit is not None:
                kv = {"Key": "AMI Commit", "Value": commit, "PropagateAtLaunch": "true"}
                self.resources[key]["Properties"]["Tags"].append(kv)

        _ami = Arg.AMI(key + "AMI", ami,
                       "AMI for the EC2 Instance '{}'".format(key))
        self.add_arg(_ami)

        _key = Arg.KeyPair(key + "Key", keypair, hostname)
        self.add_arg(_key)
        self.keypairs[hostname] = keypair

        _hostname = Arg.String(key + "Hostname", hostname,
                               "Hostname of the EC2 Instance '{}'".format(key))
        self.add_arg(_hostname)

    def add_lambda(self, key, name, role, file=None, s3=None, description="", memory=128, timeout=3, security_groups=None, subnets=None, depends_on=None):
        """Create a Python Lambda

        Args:
            key (string) : Unique name for the resource in the template
            name (string) : Function name
            role (string) : IAM role the lambda will execute under
            file (None|string) : File path to file containing lambda source code
            s3 (None|tuple) : Tuple (bucket, key, handler) for the S3 location containing lambda source code
                              handler is the Python function to execute
            description (string) : Lambda description
            memory (string|int) : Amount of memory (MB) to execute the lambda with
                                  Note, CPU is linked to the amount of memory allocated
            timeout (string|int) : Execution timeout (Seconds)
            security_groups (None|list) : List of unique names of security groups to grant the lambda access to
            subnets (None|list) : List of unique names of subnets to grant the lambda access to
            depends_on (None|string|list) : A unique name or list of unique names of resources within the
                                            configuration and is used to determine the launch order of resources
        """

        if file is not None:
            with open(file, "r") as fh:
                code = lib.json_sanitize(fh.read())
                if len(code) >= 4096:
                    raise Exception("Lambda code file is too large") # TODO need to figure out if / how to upload a manually created zip file

            code = {"ZipFile": code}
            handler = "index.handler"
        elif s3 is not None:
            bucket, key, handler = s3
            code = {
                "S3Bucket": bucket,
                "S3Key": key
            }
        else:
            raise Exception("Need source file or S3 bucket")

        memory = int(memory)
        if memory < 128 or 1536 < memory:
            raise Exception("Lambda memory should be between 128 and 1536")
        if memory % 64 != 0:
            raise Exception("Lambda memory should be a multiple of 64")

        self.resources[key] = {
            "Type" : "AWS::Lambda::Function",
            "Properties" : {
                "Code": code,
                "Description": description,
                "FunctionName": name.replace('.', '-'),
                "Handler": handler,
                "MemorySize": memory,
                "Role": {"Ref": role},
                "Runtime": "python2.7",
                "Timeout": int(timeout)
            }
        }

        if security_groups is not None and subnets is not None:
            self.resources[key]["Properties"]["VpcConfig"] = {
                "SecurityGroupIds": [{"Ref": sg} for sg in security_groups],
                "SubnetIds": [{"Ref": sub} for sub in subnets]
            }
        elif security_groups is not None or subnets is not None:
            raise Exception("security_groups and subnets should both be specified")

        if depends_on is not None:
            self.resources[key]["DependsOn"] = depends_on

    def add_lambda_permission(self, key, lambda_, action="lambda:invokeFunction", principal="sns.amazonaws.com", source=None):
        """Add permissions to a Lambda

        Args:
            key (string) : Unique name for the resource in the template
            lambda_ (string) : Unique name of the lambda resource
            action (string) : Permission action to grant the lambda
            principal (string) : AWS principal to grant the action to
            source (string) : Source ARN to restrict the permission to
        """
        self.resources[key] = {
            "Type": "AWS::Lambda::Permission",
            "Properties": {
                "Action": action,
                "FunctionName": {"Ref": lambda_},
                "Principal": principal
            }
        }

        if source is not None:
            self.resources[key]["Properties"]["SourceArn"] = source

    def _add_record_cname(self, key, hostname, vpc="VPC", ttl="300", rds=False, cluster=False, replication=False, ec2=False, elb=False):
        """Add a CNAME RecordSet to the configuration

        Note: Only one of rds/cluster/replication/ec2 should be specified for the call
        Note: cluster is not currently supported, due to Fn::GetAtt not working on ElastiCache Redis Cluster instances

        Args:
            key (string) : Unique name for the resource in the template to create the RecordSet for
            hostname (string) : The DNS hostname to map to the resource
            vpc (string) : The VPC unique name within the configuration containing the target HostedZone
            ttl (string) : The Time to live for the RecordSet
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

        zone = { "Fn::Join" : ["", [{ "Ref" : vpc + "Domain" }, "."] ]}
        target = { "Fn::GetAtt" : [ key, address_key ] }

        self.add_route_53_record_set(key + "Record", hostname, target, zone, ttl)

        if "DNSZone" in self.resources:
            self.resources[key + "Record"]["DependsOn"] = "DNSZone"

        domain = Arg.String(vpc + "Domain", self.vpc_domain,
                            "Domain of the VPC '{}'".format(vpc))
        self.add_arg(domain)

    def add_route_53_record_set(self, key, full_domain_name, cname_value, hosted_zone_name="theboss.io.", ttl=300):
        """Add a CNAME RecordSet to the configuration

        Args:
            key (string) : Unique name for the resource in the template to create the RecordSet for
            full_domain_name (string) : The FQDN DNS entry to create
            cname_value (string) : The CNAME value to return for the full_domain_name
            hosted_zone_name (string) : The name of the HostedZone (should end in a '.')
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

    def add_cloudwatch_alarm(self, key, description, statistic, metric, comparison, threashold, alarm_actions, dimensions={}, depends_on=None):
        """Add CloudWatch Alarm for a LoadBalancer

        Args:
            key (string) : Unique name for the resource in the template
            description (string) : Alarm description
            statistic (string) : Alarm statistic
            metric (string) : Statistic metric
            comparison (string) : Alarm's comparison operation
            threashold (string) : Threashold limit
            alarm_actions (list) : List of ARN string of actions to execute when the alarm is triggered
            dimensions (dict) : Dictionary of dimensions for the alarm's associated metric
            depends_on (None|string|list): A unique name or list of unique names of resources within the
                                           configuration and is used to determine the launch order of resources
        """
        self.resources[key] = {
              "Type": "AWS::CloudWatch::Alarm",
              "Properties": {
                "ActionsEnabled": "true",
                "AlarmDescription": description,
                "ComparisonOperator": comparison,
                "EvaluationPeriods": "5",
                "MetricName": metric,
                "Namespace": "AWS/ELB",
                "Period": "60",
                "Statistic": statistic,
                "Threshold": threashold,
                "AlarmActions": [alarm_actions],
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
            lb_name (string) : The LoadBalancer name
            alarm_actions (string) : The name of SNS mailing list
            depends_on (None|string|list): A unique name or list of unique names of resources within the
                                           configuration and is used to determine the launch order of resources
        """
        self.add_cloudwatch_alarm("Latency", "",
                                  "Latency", "Average", "GreaterThanOrEqualToThreshold", "2.0",
                                  alarm_actions, {"LoadBalancerName": lb_name}, depends_on)

        self.add_cloudwatch_alarm("SurgeCount", "Surge Count in Load Balance",
                                  "SurgeQueueLength", "Average", "GreaterThanOrEqualToThreshold", "3.0",
                                  alarm_actions, {"LoadBalancerName": lb_name}, depends_on)

        self.add_cloudwatch_alarm("UnhealthyHostCount", "Unhealthy Host Count in Load Balance",
                                  "UnHealthyHostCount", "Minimum", "GreaterThanOrEqualToThreshold", "1.0",
                                  alarm_actions, {"LoadBalancerName": lb_name}, depends_on)

    def add_sns_topic(self, key, name, topic, subscriptions=[]):
        """Create a SNS topic

        Args:
            key (string) : Unique name for the resource in the template
            name (string): Display name of the SNS topic
            topic (string): SNS topic name
            subscriptions (list): List of tuples containing SNS scriptions to create
                                  (protocol, endpoint)
        """
        self.resources[key] = {
            "Type": "AWS::SNS::Topic",
            "Properties": {
                "DisplayName": name,
                "Subscription": [{"Endpoint": ep, "Protocol": pt} for pt, ep in subscriptions],
                "TopicName": topic.replace('.', '-')
            }
        }

    # XXX DP: Does this work, it looks like the keys topicMicronList and snspolicyMicronList should be self.resources keys, not subkeys
    # TODO clean up function and make generic, right now topic_name is not used and there are hardcoded email addresses
    def _add_sns_topic(self, key, topic_name, depends_on=None ):
        """ Add alarms for Loadbalancer
        :arg key is the unique name (within the configuration) for this resource
        :arg name is the name to give the
        :arg depends_on is a list of resources this loadbalancer depends on
        """
        self.resources[key] = {
            "topicMicronList": {
                  "Type": "AWS::SNS::Topic",
                  "Properties": {
                    "DisplayName": "MicronList",
                    "Subscription": [
                      {
                        "Endpoint": "13012544552",
                        "Protocol": "sms"
                      },
                      {
                        "Endpoint": "sandy.hider@jhuapl.edu",
                        "Protocol": "email"
                      }
                    ]
                  }
                },
                "snspolicyMicronList": {
                  "Type": "AWS::SNS::TopicPolicy",
                  "Properties": {
                    "Topics": [
                      {
                        "Ref": "topicMicronList"
                      }
                    ],
                    "PolicyDocument": {
                      "Version": "2008-10-17",
                      "Id": "__default_policy_ID",
                      "Statement": [
                        {
                          "Sid": "__default_statement_ID",
                          "Effect": "Allow",
                          "Principal": {
                            "AWS": "*"
                          },
                          "Action": [
                            "SNS:ListSubscriptionsByTopic",
                            "SNS:Subscribe",
                            "SNS:DeleteTopic",
                            "SNS:GetTopicAttributes",
                            "SNS:Publish",
                            "SNS:RemovePermission",
                            "SNS:AddPermission",
                            "SNS:Receive",
                            "SNS:SetTopicAttributes"
                          ],
                          "Resource": {
                            "Ref": "topicMicronList"
                          },
                          "Condition": {
                            "StringEquals": {
                              "AWS:SourceOwner": "256215146792"
                            }
                          }
                        },
                        {
                          "Sid": "__console_pub_0",
                          "Effect": "Allow",
                          "Principal": {
                            "AWS": "*"
                          },
                          "Action": "SNS:Publish",
                          "Resource": {
                            "Ref": "topicMicronList"
                          }
                        },
                        {
                          "Sid": "__console_sub_0",
                          "Effect": "Allow",
                          "Principal": {
                            "AWS": "*"
                          },
                          "Action": [
                            "SNS:Subscribe",
                            "SNS:Receive"
                          ],
                          "Resource": {
                            "Ref": "topicMicronList"
                          },
                          "Condition": {
                            "StringEquals": {
                              "SNS:Protocol": [
                                "application",
                                "sms",
                                "email"
                              ]
                            }
                          }
                        }
                      ]
                    }
                  }
                }


        }
        if depends_on is not None:
            self.resources[key]["DependsOn"] = depends_on

    def add_sqs_queue(self, key, name, hide=30, retention=5760, dead=None):
        """Create a SQS Queue

        Notes:
            Maximum message size is 256KiB, which is the maximum size for SQS

        Args:
            key (string) : Unique name for the resource in the template
            name (string): Display name of the SQS queue
            hide (int) : Number of seconds to hide a queue item before it is again available for processing
            retention (int) : Number of minute a message will be retained
                              Limits are 1 minute to 14 days (default 4 days)
            dead (None|tuple) : Dead letter queue tuple (targetARN, missedDeliveries)
        """

        if retention < 1 or 20160 > retention:
            raise Exception("Rentention period is 1 minute to 14 days")

        self.resources[key] = {
            "Type": "AWS::SQS::Queue",
            "Properties": {
                "MessageRetentionPeriod": retention * 60,
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


class UserData:
    """A wrapper class around configparse.ConfigParser that automatically loads
    the default boss.config file and provide the ability to return the
    configuration file as a string. (ConfigParser can only write to a file
    object)
    """
    def __init__(self, config_file = "../salt_stack/salt/boss-tools/files/boss-tools.git/bossutils/boss.config.default"):
        self.config = configparser.ConfigParser()
        self.config.optionxform = str  # this line perserves the case of the keys.
        self.config.read(config_file)

    def __getitem__(self, key):
        return self.config[key]

    def __str__(self):
        buffer = io.StringIO()
        self.config.write(buffer)
        data = buffer.getvalue()
        buffer.close()
        return data

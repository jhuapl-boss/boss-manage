"""Configuration class and supporting classes for building and launching
CloudFormation templates.
"""

import os
import time
import json
import io
import configparser
import hosts
import library as lib


"""
Either hardcode all arguments into the template
-OR-
Construct seperate arguments dictionary

The differrence is when a configuration is generated,
the first produces something that is exactly the same
as the call to CloudFormation create_stack(), while the
second approach allows someone to upload the generated
config to CloudFormation and manually specify the values
that they want...
"""

def bool_str(val):
    """Convert a bool to a string with appropriate case formatting."""
    return "true" if val else "false"
        
class Arg:
    """Create CloudFormation template arguments of the supplied types."""
    def __init__(self, key, parameter, argument):
        """Generic constructor used by all of the specific static methods.
        key is the unique name associated with the argument.
        parameter is the dictionary of parameter information included in the
                  template.
        argument is the dictionary of value information to supply with the
                 template when launching.
        """
        self.key = key
        self.parameter = parameter
        self.argument = argument

    @staticmethod
    def String(key, value, description=""):
        """Create a String argument."""
        parameter =  {
            "Description" : description,
            "Type": "String"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)
        
    @staticmethod
    def Password(key, value, description=""):
        """Create a String argument that does not show typed characters."""
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
        """Create a VPC ID argument that makes sure the value is a valid VPC ID."""
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
        """
        parameter = {
            "Description" : description,
            "Type": "AWS::EC2::Subnet::Id"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)
        
    @staticmethod
    def AMI(key, value, description=""):
        """Create a AMI ID argument that makes sure the value is a valid AMI ID."""
        parameter = {
            "Description" : description,
            "Type": "AWS::EC2::Image::Id"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)
        
    @staticmethod
    def KeyPair(key, value, hostname):
        """Create a KeyPair KeyName argument that makes sure the value is a
        valid KeyPair name.
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
        """
        parameter = {
            "Description" : description,
            "Type" : "For whatever reason CloudFormation does not recognize RouteTable::Id",
            "Type" : "AWS::EC2::RouteTable::Id",
            "Type" : "String"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)

class CloudFormationConfiguration:
    """Configuration class that helps with building CloudFormation templates
    and launching them.
    """
    def __init__(self, domain, devices = None):
        """domain is either <vpc>.<tld> or <subnet>.<vpc>.<tld> and is used to
                  populate specific pieces of VPC and Subnet information.
        devices is a dictionary of devices for use when looking up IP addresses.
        """
        self.resources = {}
        self.parameters = {}
        self.arguments = []
        self.devices = {} if devices is None else devices
        
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
        """
        return json.dumps({"AWSTemplateFormatVersion" : "2010-09-09",
                           "Description" : description,
                           "Parameters": self.parameters,
                           "Resources": self.resources},
                          indent=4)
    
    def generate(self, name, folder):
        """Create <name>.template and <name>.arguments files in the given
        directory.
        """
        with open(os.path.join(folder, name + ".template"), "w") as fh:
            fh.write(self._create_template())
            
        with open(os.path.join(folder, name + ".arguments"), "w") as fh:
            json.dump(self.arguments, fh, indent=4)
        
    def create(self, session, name, wait = True):
        """Using the given boto3 session, launch the CloudFormation template
        that this object represents. If wait is True this method will block
        until CloudFormation is done launching the template (successfully or
        not).
        """
        for argument in self.arguments:
            if argument["ParameterValue"] is None:
                raise Exception("Could not determine argument '{}'".format(argument["ParameterKey"]))
    
        client = session.client('cloudformation')
        response = client.create_stack(
            StackName = name,
            TemplateBody = self._create_template(),
            Parameters = self.arguments
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
        """Add an Arg class instance to the internal configuration."""
        if arg.key not in self.parameters:
            self.parameters[arg.key] = arg.parameter
            self.arguments.append(arg.argument)
        
    def add_vpc(self, key="VPC"):
        """Add a VPC to the configuration.
        
        VPC name and subnet are derived from the domain given to the constructor.
        """
        self.resources[key] = {
            "Type" : "AWS::EC2::VPC",
            "Properties" : {
                "CidrBlock" : { "Ref" : key + "Subnet" },
                "Tags" : [ 
                    {"Key" : "Stack", "Value" : { "Ref" : "AWS::StackName"} },
                    {"Key" : "Name", "Value" : { "Ref" : key + "Domain"} }
                ]
            }
        }
        
        subnet = Arg.CIDR(key + "Subnet", self.vpc_subnet, 
                          "Subnet of the VPC '{}'".format(key))
        self.add_arg(subnet)
        domain = Arg.String(key + "Domain", self.vpc_domain,
                            "Domain of the VPC '{}'".format(key))
        self.add_arg(domain)

    def add_subnet(self, key="Subnet", vpc="VPC", az=None):
        """Add a Subnet to the configuration.
        
        az is the specific Availability Zone to launch the subnet in
              else AWS will decide.
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
    
    # ??? save hostname : keypair somewhere?
    def add_ec2_instance(self, key, hostname, ami, keypair, subnet="Subnet", type_="t2.micro", iface_check=True, public_ip=False, security_groups=None, user_data=None, meta_data=None, depends_on=None):
        """Add an EC2 instance to the configuration
        key is the unique name (within the configuration) for this instance
        hostname is the hostname of the machine
                 hostname is used to lookup the IP address to assign to the machine
        ami is the AMI image ID
        subnet is the Subnet unique name within the configuration to launch this machine in
        type_ is the instance type to create
        iface_check determines is the network should check if the traffic is destined for itself
                    (usedful for NAT instances)
        public_ip determines is the instance gets a public IP address
        security_groups is an array of SecurityGroup unique names within the configuration
        user_data is a string of user-data to give to the instance when launching
        meta_data is a dictionary of meta-data to include with the configuration
        depends_on the unique name of a resource within the configuration and is used to
                   determine the launch order of resources
        """
        self.resources[key] = {
            "Type" : "AWS::EC2::Instance",
            "Properties" : {
                "ImageId" : { "Ref" : key + "AMI" },
                "InstanceType" : type_,
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
                    "PrivateIpAddress"         : { "Ref" : key + "IP" }
                }]
            }
        }
        
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
        
        _hostname = Arg.String(key + "Hostname", hostname,
                               "Hostname of the EC2 Instance '{}'".format(key))
        self.add_arg(_hostname)
        
        ip = Arg.IP(key + "IP", hosts.lookup(hostname, self.devices),
                    "IP Address of the EC2 Instance '{}'".format(key))
        self.add_arg(ip)
    
    def add_rds_db(self, key, hostname, port, db_name, username, password, subnets, type_="db.t2.micro", storage="5", security_groups=None):
        """Add an RDS DB instance to the configuration
        key is the unique name (within the configuration) for this instance
        hostname is the hostname of the machine
        port is the port for the DB instance to listen on
        db_name is the name of the database to create on the DB instance
        username is the master username for the database
        password is the (plaintext) password for the master username
        subnets is an array of Subnet unique names within the configuration across
                which to create a DB SubnetGroup for the DB Instance to launch into
        type_ is the RDS instance type to create
        storage is the storage size of the database (in GB)
        security_groups is an array of SecurityGroup unique names within the configuration
        """
        self.resources[key] = {
            "Type" : "AWS::RDS::DBInstance",
            
            "Properties" : {
                "Engine" : "mysql",
                "LicenseModel" : "general-public-license",
                "EngineVersion" : "5.6.23",
                "DBInstanceClass" : type_,
                "MultiAZ" : "false",
                "StorageType" : "standard",
                "AllocatedStorage" : storage,
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
    
    def add_dynamo_db(self, key, name, attributes, key_schema, throughput):
        """Add an DynamoDB Table to the configuration
        key is the unique name (within the configuration) for this instance
        name is the name of the DynamoDB Table to create
        attributes = {AttributeName : AttributeType, ...}
        key_schema = {AttributeName : KeyType, ...}
        throughput = (ReadCapacity, WriteCapacity)
            ReadCapacity is the minimum number of consistent reads of items per second
                         before Amazon DynamoDB balances the loads
            WriteCapacity is the minimum number of consistent writes of items per second
                          before Amazon DynamoDB balances the loads
        """
        attr_defs = []
        for key in attributes:
            attr_defs.append({"AttributeName": key, "AttributeType": attributes[key]})
            
        key_schema_ = []
        for key in key_schema:
            key_schema_.append({"AttributeName": key, "KeyType": attributes[key]})
    
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
    
    def add_security_group(self, key, name, rules, vpc="VPC"):
        """Add SecurityGroup to the configuration
        key is the unique name (within the configuration) for this resource
        name is the name to give the SecurityGroup
             The name is appended with the configuration's VPC domain name
        reules is an array of tuples [(protocol, from, to, cidr)]
             Where protocol/from/to can be -1 if open access is desired
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
        """Add ReouteTable to the configuration
        key is the unique name (within the configuration) for this resource
        name is the name to give the RouteTable
            The name is appended with the configuration's VPC domain name
        subnets is a list of subnets to which the RouteTable is associated
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
        key is the unique name (within the configuration) for this resource
        route_table is the unique name of the RouteTable in the configuration
        subnet is the the unique name of the Subnet to associate the RouteTable with
        """
        self.resources[key] = {
          "Type" : "AWS::EC2::SubnetRouteTableAssociation",
          "Properties" : {
            "SubnetId" : { "Ref" : subnet },
            "RouteTableId" : { "Ref" : route_table }
          }
        }
        
    def add_route_table_route(self, key, route_table, cidr="0.0.0.0/0", gateway=None, peer=None, depends_on=None):
        """Add a Route to the configuration
        key is the unique name (within the configuration) for this resource
        route_table is the unqiue name of the RouteTable to add the route to
        cidr is the CIDR of the route
        gateway is the target internet gateway
        peer is the target VPC peer gateway
            NOTE: One and only one of gateway/peer should be specified
        depends_on is the resource that this route depends on
            Normally used when creating an InternetGateway
        """
        self.resources[key] = {
          "Type" : "AWS::EC2::Route",
          "Properties" : {
            "RouteTableId" : { "Ref" : route_table },
            "DestinationCidrBlock" : { "Ref" : key + "Cidr" },
          }
        }
        
        checks = [gateway, peer]
        check = checks.count(None)
        if len(checks) - checks.count(None) != 1:
            raise Exception("Required to specify one and only one of the following arguments: gateway|peer")
        
        
        if gateway is not None:
            self.resources[key]["Properties"]["GatewayId"] = { "Ref" : gateway }
        if peer is not None:
            self.resources[key]["Properties"]["VpcPeeringConnectionId"] = { "Ref" : peer }
           
        if depends_on is not None:
            self.resources[key]["DependsOn"] = depends_on
        
        cidr = Arg.CIDR(key + "Cidr", cidr, 
                        "Destination CIDR Block for Route '{}'".format(key))
        self.add_arg(cidr)
        
    def add_internet_gateway(self, key, name="internet", vpc="VPC"):
        """Add an InternetGateway to the configuration
        key is the unique name (within the configuration) for this resource
        name is the name to give the RouteTable
            The name is appended with the configuration's VPC domain name
        """
        self.resources[key] = {
          "Type" : "AWS::EC2::InternetGateway",
          "Properties" : {
            "Tags" : [
                {"Key" : "Stack", "Value" : { "Ref" : "AWS::StackName"} },
                {"Key" : "Name", "Value" : { "Fn::Join" : [ ".", [name, { "Ref" : vpc + "Domain" }]]}}
            ]
          }
        }
        
        self.resources["Attach" + key] = {
           "Type" : "AWS::EC2::VPCGatewayAttachment",
           "Properties" : {
             "VpcId" : { "Ref" : vpc },
             "InternetGatewayId" : { "Ref" : key }
           }
        }
        
        domain = Arg.String(vpc + "Domain", self.vpc_domain,
                            "Domain of the VPC '{}'".format(vpc))
        self.add_arg(domain)
        
    def add_vpc_peering(self, key, vpc, peer_vpc):
        """Add a VPCPeeringConnection to the configuration
        key is the unique name (within the configuration) for this resource
        vpc is the the unique name of the source VPC to create the peering connection from
        peer_vpc is the the unique name of the destination VPC to create the peering connection to
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

    def add_loadbalancer(self, key, name, instances, subnets=None, security_groups=None, depends_on=None ):
        """ Add loadbalancer to the configuration
        key is the unique name (within the configuration) for this resource
        name is the name to give the
        instances is the list of instances
        subnets is a list of subnet names
        security_groups is a list of SecurityGroups
        """
        self.resources[key] = {
            "Type": "AWS::ElasticLoadBalancing::LoadBalancer",
            "Properties": {
                #"AccessLoggingPolicy" : AccessLoggingPolicy,
                #"AppCookieStickinessPolicy" : [ AppCookieStickinessPolicy, ... ],
                #"AvailabilityZones" : [ String, ... ],  # using Subnets instead of AVs
                #"ConnectionDrainingPolicy" : ConnectionDrainingPolicy,
                #"ConnectionSettings" : ConnectionSettings,
                "CrossZone" : True,
                "HealthCheck" : {
                    "Target" : "HTTP:80/ping/",
                    "HealthyThreshold" : "2",
                    "UnhealthyThreshold" : "2",
                    "Interval" : "30",
                    "Timeout" : "5"
                },
                #"LBCookieStickinessPolicy" : [ LBCookieStickinessPolicy, ... ],
                "LoadBalancerName" : name,
                "Listeners" : [ {
                    "LoadBalancerPort" : "80",
                    "InstancePort" : "80",
                    "Protocol" : "HTTP"
                } ],
                #"Policies" : [ ElasticLoadBalancing Policy, ... ],
                #"Scheme" : String,
                "Tags" : [
                    {"Key" : "Stack", "Value" : { "Ref" : "AWS::StackName"} }
                ]
            }
        }
        if instances is not None:
            ref_insts = []
            for inst in instances:
                ref_insts.append({ "Ref" : inst })
            self.resources[key]["Properties"]["Instances"] = ref_insts
        if security_groups is not None:
            sgs = []
            for sg in security_groups:
                sgs.append({ "Ref" : sg })
            print("securityGroup Info follows:")
            print(sgs)
            self.resources[key]["Properties"]["SecurityGroups"] = sgs
        if subnets is not None:
            ref_subs = []
            for sub in subnets:
                ref_subs.append({ "Ref" : sub })
            self.resources[key]["Properties"]["Subnets"] = ref_subs
        if depends_on is not None:
            self.resources[key]["DependsOn"] = depends_on


class UserData:
    """A wrapper class around configparse.ConfigParser that automatically loads
    the default boss.config file and provide the ability to return the
    configuration file as a string. (ConfigParser can only write to a file
    object)
    """
    def __init__(self, config_file = "../salt_stack/salt/boss-tools/files/boss.config.default"):
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        
    def __getitem__(self, key):
        return self.config[key]
        
    def __str__(self):
        buffer = io.StringIO()
        self.config.write(buffer)
        data = buffer.getvalue()
        buffer.close()
        return data
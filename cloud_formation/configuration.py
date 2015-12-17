import os
import time
import json
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
    return "true" if val else "false"

class Ref:
    def __init__(self, key):
        pass
        
class Arg:
    def __init__(self, key, parameter, argument):
        self.key = key
        self.parameter = parameter
        self.argument = argument

    @staticmethod
    def String(key, value, description=""):
        parameter =  {
            "Description" : description,
            "Type": "String"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)
       
    @staticmethod
    def IP(key, value, description=""):
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
        parameter = {
            "Description" : description,
            "Type": "AWS::EC2::VPC::Id"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)
    
    @staticmethod
    def Subnet(key, value, description=""):
        parameter = {
            "Description" : description,
            "Type": "AWS::EC2::Subnet::Id"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)
        
    @staticmethod
    def AMI(key, value, description=""):
        parameter = {
            "Description" : description,
            "Type": "AWS::EC2::Image::Id"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)
        
    @staticmethod
    def KeyPair(key, value, hostname):
        parameter = {
            "Description" : "Name of an existing EC2 KeyPair to enable SSH access to '{}'".format(hostname),
            "Type": "AWS::EC2::KeyPair::KeyName",
            "ConstraintDescription" : "must be the name of an existing EC2 KeyPair."
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)

    @staticmethod
    def SecurityGroup(key, value, description=""):
        parameter = {
            "Description" : description,
            "Type": "AWS::EC2::SecurityGroup::Id"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)
    
    @staticmethod    
    def RouteTable(key, value, description=""):
        parameter = {
            "Description" : description,
            "Type" : "For whatever reason CloudFormation does not recognize RouteTable::Id",
            "Type" : "AWS::EC2::RouteTable::Id",
            "Type" : "String"
        }
        argument = lib.template_argument(key, value)
        return Arg(key, parameter, argument)

class CloudFormationConfiguration:
    def __init__(self, domain, devices = None):
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
        return json.dumps({"AWSTemplateFormatVersion" : "2010-09-09",
                           "Description" : description,
                           "Parameters": self.parameters,
                           "Resources": self.resources},
                          indent=4)
    
    def generate(self, name, folder):
        with open(os.path.join(folder, name + ".template"), "w") as fh:
            fh.write(self._create_template())
            
        with open(os.path.join(folder, name + ".arguments"), "w") as fh:
            json.dump(self.arguments, fh, indent=4)
        
    def create(self, session, name, wait = True):
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
        if arg.key not in self.parameters:
            self.parameters[arg.key] = arg.parameter
            self.arguments.append(arg.argument)
        
    def add_vpc(self, key="VPC"):
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
    def add_ec2_instance(self, key, hostname, ami, keypair, subnet="Subnet", type_="m3.medium", iface_check=False, public_ip=False, security_groups=None, user_data=None):
        """
            security_groups = [security group, ...]
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
        
        if security_groups is not None:
            sgs = []
            for sg in security_groups:
                sgs.append({ "Ref" : sg })
            self.resources[key]["Properties"]["NetworkInterfaces"][0]["GroupSet"] = sgs
            
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
        
        password_ = Arg.String(key + "Password", password,
                               "Master User Password for RDS DB Instance '{}'".format(key))
        self.add_arg(password_)
    
    def add_security_group(self, key, name, rules, vpc="VPC"):
        """
            rules = [(protocol, from, to, cidr)]
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
        """
            subnets = [subnet, ...]
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
        self.resources[key] = {
          "Type" : "AWS::EC2::SubnetRouteTableAssociation",
          "Properties" : {
            "SubnetId" : { "Ref" : subnet },
            "RouteTableId" : { "Ref" : route_table }
          }
        }
        
    def add_route_table_route(self, key, route_table, cidr="0.0.0.0/0", gateway=None, peer=None, depends_on=None):
        """
            cidr  if None use "0.0.0.0/0" else use cidr
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
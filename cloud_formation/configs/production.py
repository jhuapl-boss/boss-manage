"""Create the production environment.

ADDRESSES - the dictionary of production hostnames and subnet indexes.
DEVICES - the different device configurations to include in the template.
ROUTE - an extra route for the new VPC Peering connection.
"""

import configuration
import library as lib
import hosts
import pprint

# Devices that all VPCs/Subnets may potentially have and Subnet number (must fit under SUBNET_CIDR)
# Subnet number can be a single number or a list of numbers
ADDRESSES = {
    "api": range(10, 20),
    "db": range(20, 30),
}
       
def create_config(session, domain, keypair=None, api_token=None, db_config=None):
    config = configuration.CloudFormationConfiguration(domain, ADDRESSES)

    if config.subnet_domain is not None:
        raise Exception("Invalid VPC domain name")
        
    if session is not None and lib.vpc_id_lookup(session, domain) is not None:
        raise Exception("VPC already exists, exiting...")    
    # Allow production to be launched into an existing VPC (a core one)?
    
    config.add_vpc()
    
    config.subnet_domain = "a." + domain
    config.subnet_subnet = hosts.lookup(config.subnet_domain)
    config.add_subnet("ASubnet")
    
    config.subnet_domain = "b." + domain
    config.subnet_subnet = hosts.lookup(config.subnet_domain)
    config.add_subnet("BSubnet", az="us-east-1c") # BSubnet needs to be in a different AZ from ASubnet
    
    config.add_ec2_instance("API",
                            "api.a." + domain,
                            lib.ami_lookup(session, "web.boss"),
                            keypair,
                            subnet = "ASubnet",
                            security_groups = ["InternalSecurityGroup", "InternetSecurityGroup"],
                            user_data = api_token)
                            
    def db_key(key):
        return None if db_config is None else db_config[key]

    config.add_rds_db("DB",
                      "db.a." + domain,
                      db_key("port"),
                      db_key("name"),
                      db_key("user"),
                      db_key("password"),
                      ["ASubnet", "BSubnet"],
                      security_groups = ["InternalSecurityGroup"])
                            
    config.add_security_group("InternalSecurityGroup",
                              "internal",
                              [("-1", "-1", "-1", "10.0.0.0/8")])
                              
    config.add_security_group("InternetSecurityGroup",
                              "internet",
                              [
                                ("tcp", "22", "22", "0.0.0.0/0"),
                                ("tcp", "80", "80", "0.0.0.0/0"),
                                ("tcp", "443", "443", "0.0.0.0/0")
                              ])
                              
    config.add_route_table("InternetRouteTable",
                           "internet",
                           subnets = ["ASubnet"])
                           
    config.add_route_table_route("InternetRoute",
                                 "InternetRouteTable",
                                 gateway = "InternetGateway",
                                 depends_on = "AttachInternetGateway")
                                 
    config.add_internet_gateway("InternetGateway")
                              
    return config
                                
  
def generate(folder, domain):
    name = lib.domain_to_stackname(domain)
    config = create_config(None, domain)
    config.generate(name, folder)
                          
def create(session, domain):
    keypair = lib.keypair_lookup(session)
    core_vpc = input("Core VPC: ")
    
    def call_vault(command, *args):
        return lib.call_vault(session,
                              lib.keypair_to_file(keypair),
                              "bastion." + core_vpc,
                              "vault." + core_vpc,
                              command, *args)
    
    db = {
        "name":"boss",
        "user":"testuser",
        "password": lib.password("Django DB"),
        "host":"db.a." + domain,
        "port": "3306"
    }
    
    api_token = call_vault("vault-provision")
    call_vault("vault-django", db["name"], db["user"], db["password"], db["host"], db["port"])

    try:
        name = lib.domain_to_stackname(domain)
        config = create_config(session, domain, keypair, api_token, db)
        
        success = config.create(session, name)
        if not success:
            raise Exception("Create Failed")
    except:
        print("Error detected, revoking secrets")
        # currently no command for deleting data from Vault, just override it
        try:
            call_vault("vault-django", "", "", "", "", "")
        except:
            print("Error revoking Django credentials")
        try:
            call_vault("vault-revoke", api_token)
        except:
            print("Error revoking API Vault access token")
        raise

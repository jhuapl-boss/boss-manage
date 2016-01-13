import library as lib
import configuration
import hosts
import time
import requests

keypair = None

def create_config(session, domain):
    config = configuration.CloudFormationConfiguration(domain)

    if config.subnet_domain is not None:
        raise Exception("Invalid VPC domain name")
        
    if session is not None and lib.vpc_id_lookup(session, domain) is not None:
        raise Exception("VPC already exists, exiting...")
    
    global keypair
    keypair = lib.keypair_lookup(session)
    
    config.add_vpc()
    
    config.subnet_domain = "internal." + domain
    config.subnet_subnet = hosts.lookup(config.subnet_domain)
    config.add_subnet("InternalSubnet")
    
    config.subnet_domain = "external." + domain
    config.subnet_subnet = hosts.lookup(config.subnet_domain)
    config.add_subnet("ExternalSubnet")
    
    user_data = configuration.UserData()
    # CAUTION: This hard codes the Vault address in the config file passed and will cause
    #          problems if the template is saved and launched with a different Vault IP
    user_data["vault"]["url"] = "http://{}:8200".format(hosts.lookup("vault." + domain))
    user_data["system"]["fqdn"] = "vault." + domain
    user_data["system"]["type"] = "vault"
    
    config.add_ec2_instance("Vault",
                            "vault." + domain,
                            lib.ami_lookup(session, "vault.boss"),
                            keypair,
                            subnet = "InternalSubnet",
                            security_groups = ["InternalSecurityGroup"],
                            user_data = str(user_data))

    config.add_ec2_instance("Bastion",
                            "bastion." + domain,
                            lib.ami_lookup(session, "amzn-ami-vpc-nat-hvm-2015.03.0.x86_64-ebs"),
                            keypair,
                            subnet = "ExternalSubnet",
                            public_ip = True,
                            security_groups = ["InternalSecurityGroup", "AllSSHSecurityGroup"])
                            
    config.add_security_group("InternalSecurityGroup",
                              "internal",
                              [("-1", "-1", "-1", "10.0.0.0/8")])
                              
    config.add_security_group("AllSSHSecurityGroup",
                              "ssh",
                              [("tcp", "22", "22", "0.0.0.0/0")])
                              
    config.add_route_table("InternetRouteTable",
                           "internet",
                           subnets = ["ExternalSubnet"])
                           
    config.add_route_table_route("InternetRoute",
                                 "InternetRouteTable",
                                 gateway = "InternetGateway",
                                 depends_on = "AttachInternetGateway")
                                 
    config.add_internet_gateway("InternetGateway")
                              
    return config
                              
def generate(folder, domain):
    name = lib.domain_to_stackname("core." + domain)
    config = create_config(None, domain)
    config.generate(name, folder)
    
def create(session, domain):
    name = lib.domain_to_stackname("core." + domain)
    config = create_config(session, domain)
    
    success = config.create(session, name)
    if success:
        vpc_id = lib.vpc_id_lookup(session, domain)
        lib.rt_name_default(session, vpc_id, "internal." + domain)
        
        try:
            print("Waiting 2.5 minutes for VMs to start...")
            time.sleep(150)
            print("Initializing Vault...")
            lib.call_vault(session,
                           lib.keypair_to_file(keypair),
                           "bastion." + domain,
                           "vault." + domain,
                           "vault-init")
        except requests.exceptions.ConnectionError:
            print("Could not connect to Vault, manually initialize it before launching other machines")

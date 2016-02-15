"""
Create the production configuration which consists of
  * An endpoint web server in the external subnet
  * A RDS DB Instance launched into two new subnets (A and B)

The production configuration creates all of the resources needed to run the
BOSS system. The production configuration expects to be launched / created
in a VPC created by the core configuration. It also expects for the user to
select the same KeyPair used when creating the core configuration.

ADDRESSES - the dictionary of production hostnames and subnet indexes.
"""


import configuration
import library as lib
import hosts
import pprint

# Devices that all VPCs/Subnets may potentially have and Subnet number (must fit under SUBNET_CIDR)
# Subnet number can be a single number or a list of numbers
ADDRESSES = {
    "endpoint": range(10, 20),
    "db": range(20, 30),
}

def create_config(session, domain, keypair=None, user_data=None, db_config={}):
    """Create the CloudFormationConfiguration object."""
    config = configuration.CloudFormationConfiguration(domain, ADDRESSES)

    # do a couple of verification checks
    if config.subnet_domain is not None:
        raise Exception("Invalid VPC domain name")

    vpc_id = lib.vpc_id_lookup(session, domain)
    if session is not None and vpc_id is None:
        raise Exception("VPC does not exists, exiting...")

    # Lookup the VPC, External Subnet, Internal Security Group IDs that are
    # needed by other resources
    config.add_arg(configuration.Arg.VPC("VPC", vpc_id,
                                         "ID of VPC to create resources in"))

    external_subnet_id = lib.subnet_id_lookup(session, "external." + domain)
    config.add_arg(configuration.Arg.Subnet("ExternalSubnet",
                                            external_subnet_id,
                                            "ID of External Subnet to create resources in"))

    internal_sg_id = lib.sg_lookup(session, vpc_id, "internal." + domain)
    config.add_arg(configuration.Arg.SecurityGroup("InternalSecurityGroup",
                                                   internal_sg_id,
                                                   "ID of internal Security Group"))

    # Create the a and b subnets
    config.subnet_domain = "a." + domain
    config.subnet_subnet = hosts.lookup(config.subnet_domain)
    config.add_subnet("ASubnet", az="us-east-1b")

    config.subnet_domain = "b." + domain
    config.subnet_subnet = hosts.lookup(config.subnet_domain)
    config.add_subnet("BSubnet", az="us-east-1c") # BSubnet needs to be in a different AZ from ASubnet

    # Dynamically add the RDS instance address to the user data, so that
    # the endpoint server can access the launched DB
    # Fn::GetAtt and Fn::Join are CloudFormation template functions
    user_data_dynamic = [user_data, "\n[aws]\n",
                        "db = ", { "Fn::GetAtt" : [ "DB", "Endpoint.Address" ] }, "\n"]
    user_data_ = { "Fn::Join" : ["", user_data_dynamic]}

    config.add_ec2_instance("Endpoint",
                            "endpoint.external." + domain,
                            lib.ami_lookup(session, "endpoint.boss"),
                            keypair,
                            public_ip = True,
                            subnet = "ExternalSubnet",
                            security_groups = ["InternalSecurityGroup", "InternetSecurityGroup"],
                            user_data = user_data_,
                            depends_on = "DB") # make sure the DB is launched before we start

    config.add_rds_db("DB",
                      "db." + domain,
                      db_config.get("port"),
                      db_config.get("name"),
                      db_config.get("user"),
                      db_config.get("password"),
                      ["ASubnet", "BSubnet"],
                      security_groups = ["InternalSecurityGroup"])

    # Allow SSH/HTTP/HTTPS access to endpoint server from anywhere
    config.add_security_group("InternetSecurityGroup",
                              "internet",
                              [
                                ("tcp", "22", "22", "0.0.0.0/0"),
                                ("tcp", "80", "80", "0.0.0.0/0"),
                                ("tcp", "443", "443", "0.0.0.0/0")
                              ])
    # print("Adding AllHttpSecurityGroup")
    # config.add_security_group("AllHTTPSecurityGroup",
    #                           "http",
    #                           [("tcp", "80", "80", "0.0.0.0/0")])
    #
    # loadbalancer_name = "elb-" + domain.replace(".", "-")  #elb names can't have periods in them.
    # config.add_loadbalancer("LoadBalancer",
    #                         loadbalancer_name,
    #                         ["Endpoint"],
    #                         subnets = ["ExternalSubnet"],
    #                         security_groups=["AllHTTPSecurityGroup"],
    #                         depends_on = ["Endpoint", "AllHTTPSecurityGroup"])

    return config

def generate(folder, domain):
    """Create the configuration and save it to disk"""
    name = lib.domain_to_stackname("production." + domain)
    config = create_config(None, domain)
    config.generate(name, folder)

def create(session, domain):
    """Configure Vault, create the configuration, and launch it"""
    keypair = lib.keypair_lookup(session)

    def call_vault(command, *args, **kwargs):
        """A wrapper function around lib.call_vault() that populates most of
        the needed arguments."""
        return lib.call_vault(session,
                              lib.keypair_to_file(keypair),
                              "bastion." + domain,
                              "vault." + domain,
                              command, *args, **kwargs)

    db = {
        "name":"boss",
        "user":"testuser",
        "password": lib.generate_password(),
        "port": "3306"
    }

    # Configure Vault and create the user data config that the endpoint will
    # use for connecting to Vault and the DB instance
    endpoint_token = call_vault("vault-provision", "endpoint")
    user_data = configuration.UserData()
    # CAUTION: This hard codes the Vault address in the config file passed and will cause
    #          problems if the template is saved and launched with a different Vault IP
    user_data["vault"]["url"] = "http://{}:8200".format(hosts.lookup("vault." + domain))
    user_data["vault"]["token"] = endpoint_token
    user_data["system"]["fqdn"] = "endpoint.external." + domain
    user_data["system"]["type"] = "endpoint"
    user_data = str(user_data)

    # Should transition from vault-django to vault-write
    call_vault("vault-django", db["name"], db["user"], db["password"], db["port"])

    try:
        name = lib.domain_to_stackname("production." + domain)
        config = create_config(session, domain, keypair, user_data, db)

        success = config.create(session, name)
        if not success:
            raise Exception("Create Failed")
    except:
        print("Error detected, revoking secrets")
        # currently no command for deleting data from Vault, just override it
        try:
            call_vault("vault-django", "", "", "", "")
        except:
            print("Error revoking Django credentials")
        try:
            call_vault("vault-revoke", endpoint_token)
        except:
            print("Error revoking Endpoint Server Vault access token")
        raise

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
Create the proofreader configuration which consists of
  * An proofreader web server in the external subnet
  * A RDS DB Instance launched into two new subnets (A and B)

The proofreader configuration creates all of the resources needed to run the
proofreader site. The proofreader configuration expects to be launched / created
in a VPC created by the core configuration. It also expects for the user to
select the same KeyPair used when creating the core configuration.
"""


import configuration
import library as lib
import hosts
import uuid

INCOMING_SUBNET = "52.3.13.189/32" # microns-bastion elastic IP

VAULT_DJANGO = "secret/proofreader/django"
VAULT_DJANGO_DB = "secret/proofreader/django/db"
VAULT_DJANGO_AUTH = "secret/proofreader/auth"

def create_config(session, domain, keypair=None, user_data=None, db_config={}):
    """Create the CloudFormationConfiguration object."""
    config = configuration.CloudFormationConfiguration(domain)

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

    internet_sg_key = "InternetSecurityGroup"
    internet_sg_id = lib.sg_lookup(session, vpc_id, "internet." + domain)
    if internet_sg_id is None:
        # Allow SSH/HTTP/HTTPS access to proofreader web server from anywhere
        config.add_security_group(internet_sg_key,
                                  "internet",
                                  [
                                    ("tcp", "22", "22", INCOMING_SUBNET),
                                    ("tcp", "80", "80", "0.0.0.0/0"),
                                    ("tcp", "443", "443", "0.0.0.0/0")
                                  ])
    else:
        config.add_arg(configuration.Arg.SecurityGroup(internet_sg_key,
                                                       internet_sg_id,
                                                       "ID of internal Security Group"))

    az_subnets, _ = config.find_all_availability_zones(session)

    config.add_ec2_instance("ProofreaderWeb",
                            "proofreader-web." + domain,
                            lib.ami_lookup(session, "proofreader-web.boss"),
                            keypair,
                            public_ip = True,
                            subnet = "ExternalSubnet",
                            security_groups = ["InternalSecurityGroup", "InternetSecurityGroup"],
                            user_data = user_data,
                            depends_on = "ProofreaderDB") # make sure the DB is launched before we start

    config.add_rds_db("ProofreaderDB",
                      "proofreader-db." + domain,
                      db_config.get("port"),
                      db_config.get("name"),
                      db_config.get("user"),
                      db_config.get("password"),
                      az_subnets,
                      security_groups = ["InternalSecurityGroup"])

    return config

def generate(folder, domain):
    """Create the configuration and save it to disk"""
    name = lib.domain_to_stackname("proofreader." + domain)
    config = create_config(None, domain)
    config.generate(name, folder)

def create(session, domain):
    """Configure Vault, create the configuration, and launch it"""
    keypair = lib.keypair_lookup(session)

    call = lib.ExternalCalls(session, keypair, domain)

    db = {
        "name": "microns_proofreader",
        "user": "proofreader",
        "password": lib.generate_password(),
        "port": "3306"
    }

    # Configure Vault and create the user data config that proofreader-web will
    # use for connecting to Vault and the DB instance
    proofreader_token = call.vault("vault-provision", "proofreader")
    user_data = configuration.UserData()
    user_data["vault"]["token"] = proofreader_token
    user_data["system"]["fqdn"] = "proofreader-web." + domain
    user_data["system"]["type"] = "proofreader-web"
    user_data["aws"]["db"] = "proofreader-db." + domain
    user_data["auth"]["OIDC_VERIFY_SSL"] = str(domain in hosts.BASE_DOMAIN_CERTS.keys())  # TODO SH change to True once we get wildcard domain working correctly
    user_data = str(user_data)


    # Should transition from vault-django to vault-write
    call.vault_write(VAULT_DJANGO, secret_key = str(uuid.uuid4()))
    call.vault_write(VAULT_DJANGO_DB, **db)

    try:
        name = lib.domain_to_stackname("proofreader." + domain)
        config = create_config(session, domain, keypair, user_data, db)

        success = config.create(session, name)
        if not success:
            raise Exception("Create Failed")
        else:
            post_init(session, domain)

    except:
        print("Error detected, revoking secrets") # Do we want to revoke if an exception from post_init?
        try:
            call.vault_delete(VAULT_DJANGO)
            call.vault_delete(VAULT_DJANGO_DB)
        except:
            print("Error revoking Django credentials")
        try:
            call.vault("vault-revoke", proofreader_token)
        except:
            print("Error revoking Proofreader Server Vault access token")
        raise

def post_init(session, domain):
    keypair = lib.keypair_lookup(session)
    call = lib.ExternalCalls(session, keypair, domain)
    creds = call.vault_read("secret/auth")

    print("Configuring KeyCloak") # Should abstract for production and proofreader
    def configure_auth(auth_port):
        # NOTE DP: If an ELB is created the public_uri should be the Public DNS Name
        #          of the ELB. Endpoint Django instances may have to be restarted if running.
        dns = lib.instance_public_lookup(session, "proofreader-web." + domain)
        uri = "http://{}".format(dns)
        call.vault_update(VAULT_DJANGO_AUTH, public_uri = uri)

        kc = lib.KeyCloakClient("http://localhost:{}".format(auth_port))
        kc.login(creds["username"], creds["password"])
        kc.append_list_properties("BOSS", "endpoint", {"redirectUris": uri + "/*", "webOrigins": uri})
        kc.logout()
    call.set_ssh_target("auth")
    call.ssh_tunnel(configure_auth, 8080)

    print("Initializing Django")
    call.set_ssh_target("proofreader-web")
    migrate_cmd = "sudo python3 /srv/www/app/proofreader_apis/manage.py "
    call.ssh(migrate_cmd + "makemigrations") # will hang if it cannot contact the auth server
    call.ssh(migrate_cmd + "makemigrations common")
    call.ssh(migrate_cmd + "makemigrations bossoidc")
    call.ssh(migrate_cmd + "migrate")
    call.ssh(migrate_cmd + "collectstatic --no-input")
    call.ssh("sudo service uwsgi-emperor reload")
    call.ssh("sudo service nginx restart")

    print("Generating keycloak.json")
    if domain in hosts.BASE_DOMAIN_CERTS.keys():
        elb = "auth." + hosts.BASE_DOMAIN_CERTS[domain]
    else:
        elb = "auth.{}.{}".format(domain.split(".")[0],
                                  hosts.DEV_DOMAIN)

    kc = lib.KeyCloakClient("https://{}:{}".format(elb, 443), verify_ssl=False)
    kc.login(creds["username"], creds["password"])
    client_install = kc.get_client_installation_url("BOSS", "endpoint")

    # NOTE: This will put a valid bearer token in the bash history until the history is cleared
    call.ssh("sudo wget --header=\"{}\" --no-check-certificate {} -O /srv/www/html/keycloak.json"
             .format(client_install["headers"], client_install["url"]))
    # clear the history
    call.ssh("history -c")

    # this should invalidate the token anyways
    kc.logout()

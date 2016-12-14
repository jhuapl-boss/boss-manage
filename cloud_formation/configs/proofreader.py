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

from lib.cloudformation import CloudFormationConfiguration, Arg, Ref
from lib.userdata import UserData
from lib.names import AWSNames
from lib.keycloak import KeyCloakClient
from lib.external import ExternalCalls
from lib import aws
from lib import utils
from lib import scalyr
from lib import constants as const

import uuid

def create_config(session, domain, keypair=None, user_data=None, db_config={}):
    """Create the CloudFormationConfiguration object."""
    names = AWSNames(domain)
    config = CloudFormationConfiguration('proofreader', domain, const.REGION)

    vpc_id = config.find_vpc(session)
    az_subnets, _ = config.find_all_availability_zones(session)

    external_subnet_id = aws.subnet_id_lookup(session, names.subnet("external"))
    config.add_arg(Arg.Subnet("ExternalSubnet",
                              external_subnet_id,
                              "ID of External Subnet to create resources in"))

    sgs = aws.sg_lookup_all(session, vpc_id)

    # Only allow unsecure web access from APL, until a ELB is configured for HTTPS
    config.add_security_group("HttpSecurityGroup",
                              names.http,
                              [("tcp", "80", "80", const.INCOMING_SUBNET)])

    config.add_ec2_instance("ProofreaderWeb",
                            names.proofreader,
                            aws.ami_lookup(session, "proofreader-web.boss"),
                            keypair,
                            public_ip = True,
                            subnet = Ref("ExternalSubnet"),
                            security_groups = [sgs[names.internal],
                                               sgs[names.ssh],
                                               Ref('HttpSecurityGroup')],
                            user_data = user_data,
                            depends_on = "ProofreaderDB") # make sure the DB is launched before we start

    config.add_rds_db("ProofreaderDB",
                      names.proofreader_db,
                      db_config.get("port"),
                      db_config.get("name"),
                      db_config.get("user"),
                      db_config.get("password"),
                      az_subnets,
                      security_groups = [sgs[names.internal]])

    return config

def generate(session, domain):
    """Create the configuration and save it to disk"""
    config = create_config(session, domain)
    config.generate()

def create(session, domain):
    """Configure Vault, create the configuration, and launch it"""
    keypair = aws.keypair_lookup(session)

    names = AWSNames(domain)
    call = ExternalCalls(session, keypair, domain)

    db = {
        "name": "microns_proofreader",
        "user": "proofreader",
        "password": utils.generate_password(),
        "port": "3306"
    }

    # Configure Vault and create the user data config that proofreader-web will
    # use for connecting to Vault and the DB instance
    # DP TODO: Remove token and use AWS-EC2 authentication with Vault
    with call.vault() as vault:
        proofreader_token = vault.provision("proofreader")

        user_data = UserData()
        user_data["vault"]["token"] = proofreader_token
        user_data["system"]["fqdn"] = names.proofreader
        user_data["system"]["type"] = "proofreader-web"
        user_data["aws"]["db"] = names.proofreader_db
        user_data["auth"]["OIDC_VERIFY_SSL"] = 'True'
        user_data = str(user_data)

        vault.write(const.VAULT_PROOFREAD, secret_key = str(uuid.uuid4()))
        vault.write(const.VAULT_PROOFREAD_DB, **db)

    config = create_config(session, domain, keypair, user_data, db)

    try:
        success = config.create(session)
    except:
        print("Error detected, revoking secrets") # Do we want to revoke if an exception from post_init?
        with call.vault() as vault:
            try:
                vault.delete(const.VAULT_PROOFREAD)
                vault.delete(const.VAULT_PROOFREAD_DB)
            except:
                print("Error revoking Django credentials")

            try:
                vault.revoke(proofreader_token)
            except:
                print("Error revoking Proofreader Server Vault access token")
        raise

    if not success:
        raise Exception("Create Failed")
    else:
        post_init(session, domain)

def post_init(session, domain):
    keypair = aws.keypair_lookup(session)
    call = ExternalCalls(session, keypair, domain)
    names = AWSNames(domain)

    # Get Keycloak admin account credentials
    with call.vault() as vault:
        creds = vault.read("secret/auth")

        # Get Keycloak public address
        auth_url = "https://{}/".format(names.public_dns("auth"))

        # Write data into Vault
        dns = aws.instance_public_lookup(session, names.proofreader)
        uri = "http://{}".format(dns)
        vault.update(const.VAULT_PROOFREAD_AUTH, public_uri = uri)

    # Verify Keycloak is accessible
    print("Checking for Keycloak availability")
    call.check_url(auth_url + "auth/", const.TIMEOUT_KEYCLOAK)

    with KeyCloakClient(auth_url, **creds) as kc:
        print("Configuring KeyCloak")
        kc.append_list_properties("BOSS", "endpoint", {"redirectUris": uri + "/*", "webOrigins": uri})

        print("Generating keycloak.json")
        client_install = kc.get_client_installation_url("BOSS", "endpoint")

        # Verify Django install doesn't have any issues
        print("Checking Django status")
        call.check_django("proofreader-web", "/srv/www/app/proofreader_apis/manage.py")

        print("Initializing Django")
        with call.ssh(names.proofreader) as ssh:
            def django(cmd):
                ret = ssh("sudo python3 /srv/www/app/proofreader_apis/manage.py " + cmd)
                if ret != 0:
                    print("Django command '{}' did not sucessfully execute".format(cmd))

            django("makemigrations") # will hang if it cannot contact the auth server
            django("makemigrations common")
            django("makemigrations bossoidc")
            django("migrate")
            django("collectstatic --no-input")

            ssh("sudo service uwsgi-emperor reload")
            ssh("sudo service nginx restart")

            # NOTE: This will put a valid bearer token in the bash history until the history is cleared
            ssh("sudo wget --header=\"{}\" --no-check-certificate {} -O /srv/www/html/keycloak.json"
                     .format(client_install["headers"], client_install["url"]))
            # clear the history
            ssh("history -c")


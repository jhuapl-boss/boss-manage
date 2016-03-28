"""
Create the core configuration which consists of
  * A new VPC
  * An internal subnet containing a Vault server
  * An external subnet containing a Bastion server

The core configuration create all of the infrastructure that is required for
the other production resources to function. In the furture this may include
other servers for services like Authentication.
"""

import library as lib
import configuration
import hosts
import time
import requests
import scalyr

import json, traceback, os
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError

keypair = None

# Region core is created in.  Later versions of boto3 should allow us to
# extract this from the session variable.  Hard coding for now.
CORE_REGION = 'us-east-1'

INCOMING_SUBNET = "52.3.13.189/32" # microns-bastion elastic IP

def create_config(session, domain):
    """Create the CloudFormationConfiguration object."""
    config = configuration.CloudFormationConfiguration(domain, CORE_REGION)

    if config.subnet_domain is not None:
        raise Exception("Invalid VPC domain name")

    vpc_id = lib.vpc_id_lookup(session, domain)
    if session is not None and vpc_id is None:
        raise Exception("VPC does not exists, exiting...")

    global keypair
    keypair = lib.keypair_lookup(session)

    config.add_arg(configuration.Arg.VPC("VPC", vpc_id,
                                         "ID of VPC to create resources in"))

    internal_subnet_id = lib.subnet_id_lookup(session, "external." + domain)
    config.add_arg(configuration.Arg.Subnet("ExternalSubnet",
                                            internal_subnet_id,
                                            "ID of External Subnet to create resources in"))

    internal_sg_id = lib.sg_lookup(session, vpc_id, "internal." + domain)
    config.add_arg(configuration.Arg.SecurityGroup("InternalSecurityGroup",
                                                   internal_sg_id,
                                                   "ID of internal Security Group"))

    config.add_ec2_instance("Auth",
                            "auth." + domain,
                            lib.ami_lookup(session, "auth.boss"),
                            keypair,
                            subnet = "ExternalSubnet",
                            public_ip = True,
                            security_groups = ["InternalSecurityGroup", "AuthSecurityGroup"])

    config.add_security_group("AuthSecurityGroup",
                              "http",
                              [("tcp", "80", "80", "128.244.0.0/16"),
                               ("tcp", "22", "22", INCOMING_SUBNET)])

    return config

def make_auth_request(url, params = None, headers = {}, convert = urlencode):
    request = Request(
        url,
        data = None if params is None else convert(params).encode("utf-8"),
        headers = headers
    )

    try:
        response = urlopen(request).read().decode("utf-8")
        if len(response) > 0:
            response = json.loads(response)
        return response
    except HTTPError as e:
        print("Error on '{}'".format(url))
        print(e)
        return None

def upload_realm_config(port, password):
    URL = "http://localhost:{}".format(port)

    token = make_auth_request(
        URL + "/auth/realms/master/protocol/openid-connect/token",
        params = {
            "username": "admin",
            "password": password,
            "grant_type": "password",
            "client_id": "admin-cli",
        },
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
    )

    cur_dir = os.path.dirname(os.path.realpath(__file__))
    realm_file = os.path.normpath(os.path.join(cur_dir, "..", "..", "salt_stack", "salt", "keycloak", "files", "BOSS.realm"))
    print("Opening realm file at '{}'".format(realm_file))
    with open(realm_file, "r") as fh:
        realm = json.load(fh)

    resp = make_auth_request(
        URL + "/auth/admin/realms",
        params = realm,
        headers = {
            "Authorization": "Bearer " + token["access_token"],
            "Content-Type": "application/json",
        },
        convert = json.dumps
    )

    make_auth_request( # no response
        URL + "/auth/realms/master/protocol/openid-connect/logout",
        params = {
            "refresh_token": token["refresh_token"],
            "client_id": "admin-cli",
        },
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
    )

def configure_keycloak(session):
    # NOTE DP: if there is an ELB in front of the auth server, this needs to be
    #          the public DNS address of the ELB.
    auth_dns = lib.instance_public_lookup(session, "auth". domain)
    auth_discovery_url = "http://{}:8080/auth/realms/BOSS".format(auth_dns)

    password = lib.generate_password()
    print("Setting Admin password to: " + password)

    def ssh(cmd):
        lib.call_ssh(session, lib.keypair_to_file(keypair), "bastion." + domain, "auth." + domain, cmd)
    def ssh_tunnel(cmd, port):
        lib.call_ssh_tunnel(session, lib.keypair_to_file(keypair), "bastion." + domain, "auth." + domain, cmd, port)
    def vault_write(cmd, *args, **kwargs):
        lib.call_vault(session, lib.keypair_to_file(keypair), "bastion." + domain, "vault." + domain, "vault-write", *args, **kwargs)

    vault_write("secret/auth", password = password, username = "admin")
    vault_write("secret/endpoint/auth", url = auth_discovery_url, client_id = "endpoint")

    ssh("/srv/keycloak/bin/add-user.sh -r master -u admin -p " + password)
    ssh("sudo service keycloak restart")
    ssh_tunnel(lambda p: upload_realm_config(p, password), 8080)

def generate(folder, domain):
    """Create the configuration and save it to disk"""
    name = lib.domain_to_stackname("auth." + domain)
    config = create_config(None, domain)
    config.generate(name, folder)

def create(session, domain):
    """Create the configuration, launch it, and initialize Vault"""
    name = lib.domain_to_stackname("auth." + domain)
    config = create_config(session, domain)

    success = config.create(session, name)
    if success:
        try:
            time.sleep(15)
            configure_keycloak(session)
        except requests.exceptions.ConnectionError:
            print("Could not connect to Vault")

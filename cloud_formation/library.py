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

"""Library for common methods that are used by the different configs scripts."""

import sys
import os
import json
import pprint
import time
import getpass
import string
import subprocess
import shlex
import traceback
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError


import hosts

# Add a reference to boss-manage/vault/ so that we can import those files
cur_dir = os.path.dirname(os.path.realpath(__file__))
vault_dir = os.path.normpath(os.path.join(cur_dir, "..", "vault"))
sys.path.append(vault_dir)
import bastion
import vault


def get_commit():
    try:
        cmd = "git rev-parse HEAD"
        result = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE)
        return result.stdout.decode("utf-8").strip()
    except:
        return "unknown"


def domain_to_stackname(domain):
    """Create a CloudFormation Stackname from domain name by removing '.' and
    capitalizing each part of the domain.
    """
    return "".join(map(lambda x: x.capitalize(), domain.split(".")))


def template_argument(key, value, use_previous = False):
    """Create a JSON dictionary formated as a CloudFlormation template
    argument.

    use_previous is passed as UserPreviousValue to CloudFlormation.
    """
    return {"ParameterKey": key, "ParameterValue": value, "UsePreviousValue": use_previous}


def keypair_to_file(keypair):
    """Look for a ssh key named <keypair> and alert if it does not exist."""
    file = os.path.expanduser("~/.ssh/{}.pem".format(keypair))
    if not os.path.exists(file):
        print("Error: SSH Key '{}' does not exist".format(file))
        return None
    return file


def call_vault(session, bastion_key, bastion_host, vault_host, command, *args, **kwargs):
    """Call ../vault/bastion.py with a list of hardcoded AWS / SSH arguments.
    This is a common function for any other function that needs to populate
    or provision Vault when starting up new VMs.
    """
    bastion_ip = bastion.machine_lookup(session, bastion_host)
    vault_ip = bastion.machine_lookup(session, vault_host, public_ip = False)
    def cmd():
        # Have to dynamically lookup the function because vault.COMMANDS
        # references the command line version of the commands we want to execute
        return vault.__dict__[command.replace('-','_')](*args, machine=vault_host, **kwargs)

    return bastion.connect_vault(bastion_key, vault_ip, bastion_ip, cmd)


def call_ssh(session, bastion_key, bastion_host, target_host, command):
    """Call ../vault/bastion.py with a list of hardcoded AWS / SSH arguments.
    This is a common function for any other function that needs to execute an
    SSH command on a new VM.
    """
    bastion_ip = bastion.machine_lookup(session, bastion_host)
    target_ip = bastion.machine_lookup(session, target_host, public_ip = False)

    return bastion.ssh_cmd(bastion_key, target_ip, bastion_ip, command)


def call_ssh_tunnel(session, bastion_key, bastion_host, target_host, command, port, local_port = None):
    """Call ../vault/bastion.py with a list of hardcoded AWS / SSH arguments.
    This is a common function for any other function that needs to execute an
    arbitrary command within a SSH tunnel.
    """
    bastion_ip = bastion.machine_lookup(session, bastion_host)
    target_ip = bastion.machine_lookup(session, target_host, public_ip = False)

    return bastion.ssh_tunnel(bastion_key, target_ip, bastion_ip, port, local_port, command)


def password(what):
    """Prompt the user for a password and verify it."""
    while True:
        pass_ = getpass.getpass("{} Password: ".format(what))
        pass__ = getpass.getpass("Verify {} Password: ".format(what))
        if pass_ == pass__:
            return pass_
        else:
            print("Passwords didn't match, try again.")


def generate_password(length = 16):
    """Generate an alphanumeric password of the given length."""
    chars = string.ascii_letters + string.digits #+ string.punctuation
    return "".join([chars[c % len(chars)] for c in os.urandom(length)])


class KeyCloakClient:
    def __init__(self, url_base):
        self.url_base = url_base
        self.token = None

    def request(self, url, params = None, headers = {}, convert = urlencode, method = None):
        request = Request(
            self.url_base + url,
            data = None if params is None else convert(params).encode("utf-8"),
            headers = headers,
            method = method
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

    def login(self, username, password):
        self.token = self.request(
            "/auth/realms/master/protocol/openid-connect/token",
            params = {
                "username": username,
                "password": password,
                "grant_type": "password",
                "client_id": "admin-cli",
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )

        if self.token is None:
            print("Could not authenticate to KeyCloak Server")

    def logout(self):
        if self.token is None:
            return

        self.request( # no response
            "/auth/realms/master/protocol/openid-connect/logout",
            params={
                "refresh_token": self.token["refresh_token"],
                "client_id": "admin-cli",
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )

        self.token = None

    def create_realm(self, realm):
        resp = self.request(
            "/auth/admin/realms",
            params = realm,
            headers={
                "Authorization": "Bearer " + self.token["access_token"],
                "Content-Type": "application/json",
            },
            convert = json.dumps
        )

    def get_client(self, realm_name, client_id):
        resp = self.request(
            "/auth/admin/realms/{}/clients".format(realm_name),
            headers={
                "Authorization": "Bearer " + self.token["access_token"],
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )

        if resp is None:
            return None

        for client in resp:
            if client['clientId'] == client_id:
                return client
        return None

    def update_client(self, realm_name, id, client):
        resp = self.request(
            "/auth/admin/realms/{}/clients/{}".format(realm_name, id),
            params = client,
            headers={
                "Authorization": "Bearer " + self.token["access_token"],
                "Content-Type": "application/json",
            },
            convert=json.dumps,
            method="PUT"
        )

    def add_redirect_uri(self, realm_name, client_id, uri):
        client = self.get_client(realm_name, client_id)

        key = "redirectUris"
        if key not in client:
            client[key] = []
        client[key].append(uri) # DP: should probably check to see if the uri exists first

        self.update_client(realm_name, client['id'], client)

class ExternalCalls:
    def __init__(self, session, keypair, domain):
        self.session = session
        self.keypair_file = keypair_to_file(keypair)
        self.bastion_hostname = "bastion." + domain
        self.vault_hostname = "vault." + domain
        self.domain = domain
        self.ssh_target = None

    def vault(self, cmd, *args, **kwargs):
        return call_vault(self.session,
                          self.keypair_file,
                          self.bastion_hostname,
                          self.vault_hostname,
                          cmd, *args, **kwargs)

    def vault_write(self, path, **kwargs):
        self.vault("vault-write", path, **kwargs)

    def vault_update(self, path, **kwargs):
        self.vault("vault-update", path, **kwargs)

    def vault_read(self, path):
        res = self.vault("vault-read", path)
        return None if res is None else res['data']

    def vault_delete(self, path):
        self.vault("vault-delete", path)

    def set_ssh_target(self, target):
        self.ssh_target = target
        if not target.endswith("." + self.domain):
            self.ssh_target += "." + self.domain

    def ssh(self, cmd):
        if self.ssh_target is None:
            raise Exception("No SSH Target Set")

        call_ssh(self.session,
                 self.keypair_file,
                 self.bastion_hostname,
                 self.ssh_target,
                 cmd)

    def ssh_tunnel(self, cmd, port):
        if self.ssh_target is None:
            raise Exception("No SSH Target Set")

        call_ssh_tunnel(self.session,
                        self.keypair_file,
                        self.bastion_hostname,
                        self.ssh_target,
                        cmd, port)

def vpc_id_lookup(session, vpc_domain):
    """Lookup the Id for the VPC with the given domain name."""
    if session is None: return None

    client = session.client('ec2')
    response = client.describe_vpcs(Filters=[{"Name":"tag:Name", "Values":[vpc_domain]}])
    if len(response['Vpcs']) == 0:
        return None
    else:
        return response['Vpcs'][0]['VpcId']


def subnet_id_lookup(session, subnet_domain):
    """Lookup the Id for the Subnet with the given domain name."""
    if session is None: return None

    client = session.client('ec2')
    response = client.describe_subnets(Filters=[{"Name":"tag:Name", "Values":[subnet_domain]}])
    if len(response['Subnets']) == 0:
        return None
    else:
        return response['Subnets'][0]['SubnetId']


def azs_lookup(session):
    """Lookup all of the Availablity Zones for the connected region."""
    if session is None: return []

    client = session.client('ec2')
    response = client.describe_availability_zones()
    rtn = [(z["ZoneName"], z["ZoneName"][-1]) for z in response["AvailabilityZones"]]

    return rtn


def _find(xs, predicate):
    for x in xs:
        if predicate(x):
            return x
    return None


def ami_lookup(session, ami_name):
    """Lookup the Id for the AMI with the given name."""
    if session is None: return None

    if ami_name.endswith(".boss"):
        AMI_VERSION = os.environ["AMI_VERSION"]
        if AMI_VERSION == "latest":
            # limit latest searching to only versions tagged with hash information
            ami_name += "-h*"
        else:
            ami_name += "-" + AMI_VERSION

    client = session.client('ec2')
    response = client.describe_images(Filters=[{"Name":"name", "Values":[ami_name]}])
    if len(response['Images']) == 0:
        return None
    else:
        response['Images'].sort(key=lambda x: x["CreationDate"], reverse=True)
        image = response['Images'][0]
        ami = image['ImageId']
        tag = _find(image.get('Tags',[]), lambda x: x["Key"] == "Commit")
        commit = None if tag is None else tag["Value"]

        return (ami, commit)


def sg_lookup(session, vpc_id, group_name):
    """Lookup the Id for the VPC Security Group with the given name."""
    if session is None: return None

    client = session.client('ec2')
    response = client.describe_security_groups(Filters=[{"Name":"vpc-id", "Values":[vpc_id]},
                                                        {"Name":"tag:Name", "Values":[group_name]}])

    if len(response['SecurityGroups']) == 0:
        return None
    else:
        return response['SecurityGroups'][0]['GroupId']


def rt_lookup(session, vpc_id, rt_name):
    """Lookup the Id for the VPC Route Table with the given name."""
    if session is None: return None

    client = session.client('ec2')
    response = client.describe_route_tables(Filters=[{"Name":"vpc-id", "Values":[vpc_id]},
                                                     {"Name":"tag:Name", "Values":[rt_name]}])

    if len(response['RouteTables']) == 0:
        return None
    else:
        return response['RouteTables'][0]['RouteTableId']


def rt_name_default(session, vpc_id, new_rt_name):
    """Find the default VPC Route Table and give it a name so that it can be referenced latter.
    Needed because by default the Route Table does not have a name and rt_lookup() will not find it. """

    client = session.client('ec2')
    response = client.describe_route_tables(Filters=[{"Name":"vpc-id", "Values":[vpc_id]}])
    rt_id = response['RouteTables'][0]['RouteTableId'] # TODO: verify that Tags does not already have a name tag

    resource = session.resource('ec2')
    rt = resource.RouteTable(rt_id)
    response = rt.create_tags(Tags=[{"Key": "Name", "Value": new_rt_name}])


def peering_lookup(session, from_id, to_id):
    """Lookup the Id for the Peering Connection between the two VPCs."""
    if session is None: return None

    client = session.client('ec2')
    response = client.describe_vpc_peering_connections(Filters=[{"Name":"requester-vpc-info.vpc-id", "Values":[from_id]},
                                                                {"Name":"requester-vpc-info.owner-id", "Values":["256215146792"]},
                                                                {"Name":"accepter-vpc-info.vpc-id", "Values":[to_id]},
                                                                {"Name":"accepter-vpc-info.owner-id", "Values":["256215146792"]},
                                                                {"Name":"status-code", "Values":["active"]},
                                                                ])

    if len(response['VpcPeeringConnections']) == 0:
        return None
    else:
        return response['VpcPeeringConnections'][0]['VpcPeeringConnectionId']


def keypair_lookup(session):
    """Print the valid key pairs for the session and ask the user which to use."""
    if session is None: return None

    client = session.client('ec2')
    response = client.describe_key_pairs()
    print("Key Pairs")
    for i in range(len(response['KeyPairs'])):
        print("{}:  {}".format(i, response['KeyPairs'][i]['KeyName']))
    if len(response['KeyPairs']) == 0:
        return None
    while True:
        try:
            idx = input("[0]: ")
            idx = int(idx if len(idx) > 0 else "0")
            return response['KeyPairs'][idx]['KeyName']
        except:
            print("Invalid Key Pair number, try again")


def instanceid_lookup(session, hostname):
    """Look up instance id by hostname."""
    if session is None: return None

    client = session.client('ec2')
    response = client.describe_instances(
        Filters=[{"Name":"tag:Name", "Values":[hostname]}])

    item = response['Reservations']
    if len(item) == 0:
        return None
    else:
        item = item[0]['Instances']
        if len(item) == 0:
            return None
        else:
            item = item[0]
            if 'InstanceId' in item:
                return item['InstanceId']
            return None

def cert_arn_lookup(session, domain_name):
    """
    Looks up the arn for a domain_name certificate
    Args:
        session: amazon session
        domain_name: domain name the certificate was issued for.

    Returns:
        (string): arn
    """
    if session is None: return None

    client = session.client('acm')
    response = client.list_certificates()
    for certs in response['CertificateSummaryList']:
        if certs['DomainName'] == domain_name:
            return certs['CertificateArn']
    return None


def instance_public_lookup(session, hostname):
    """Look up instance id by hostname."""
    if session is None: return None

    client = session.client('ec2')
    response = client.describe_instances(
        Filters=[{"Name": "tag:Name", "Values": [hostname]},
                 {"Name": "instance-state-name", "Values": ["running"]}])

    item = response['Reservations']
    if len(item) == 0:
        return None
    else:
        item = item[0]['Instances']
        if len(item) == 0:
            return None
        else:
            item = item[0]
            if 'PublicDnsName' in item:
                return item['PublicDnsName']
            return None

def elb_public_lookup(session, hostname):
    """Look up instance id by hostname."""
    if session is None: return None

    client = session.client('elb')
    responses = client.describe_load_balancers()

    hostname_ = hostname.replace(".", "-")

    for response in responses["LoadBalancerDescriptions"]:
        if response["LoadBalancerName"].startswith(hostname_):
            return response["DNSName"]
    return None

def create_elb_listener(loadbalancer_port, instance_port, protocol, ssl_cert_id=None):
    """
    Creates an elastic loadbalancer listener
    Args:
        loadbalancer_port (string): string representation of port listening on
        instance_port (string): string representation of port on instance elb sends to
        protocol (string): protocol used, ex: HTTP, HTTPS
        ssl_cert_id:

    Returns: a map of the listener properly formatted

    """
    listener = {
        "LoadBalancerPort": loadbalancer_port,
        "InstancePort": instance_port,
        "Protocol": protocol,
    }
    if ssl_cert_id is not None:
        listener["SSLCertificateId"] = ssl_cert_id
    return listener


def lb_lookup(session, lb_name):
    """
    Lookup the Id for the loadbalancer with the given name.
    Args:
        session: session information used to peform lookups
        lb_name: loadbalancer name to lookup

    Returns: true if a valid loadbalancer name

    """
    if session is None: return None

    client = session.client('elb')
    response = client.describe_load_balancers()#Filters=[{"LoadBalancerName":lb_name}])

    value = response['LoadBalancerDescriptions'][0]['LoadBalancerName']

    for i in range(len(response['LoadBalancerDescriptions'])):
        if (response['LoadBalancerDescriptions'][i]['LoadBalancerName']) == lb_name:
            return True
    return False


def sns_topic_lookup(session, topic_name):
    """
    Lookups up SNS topic ARN given a topic name
    Args:
        session: session information to perform lookups
        topic_name: name of the topic

    Returns: ARN for the topic or None if topic doesn't exist

    """
    if session is None: return None

    client = session.client('sns')
    response = client.list_topics()
    topics_list = response['Topics']
    for topic in topics_list:
        arn_topic_name = topic["TopicArn"].split(':').pop()
        if arn_topic_name == topic_name:
            return topic["TopicArn"]
    return None

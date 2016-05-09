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
import ssl
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


def template_argument(key, value, use_previous=False):
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


def password(what):
    """Prompt the user for a password and verify it."""
    while True:
        pass_ = getpass.getpass("{} Password: ".format(what))
        pass__ = getpass.getpass("Verify {} Password: ".format(what))
        if pass_ == pass__:
            return pass_
        else:
            print("Passwords didn't match, try again.")


def generate_password(length=16):
    """
    Generate an alphanumeric password of the given length.
    Args:
        length: length of the password to be generated

    Returns:
        password
    """
    chars = string.ascii_letters + string.digits  #+ string.punctuation
    return "".join([chars[c % len(chars)] for c in os.urandom(length)])


class KeyCloakClient:
    def __init__(self, url_base, verify_ssl=True):
        self.url_base = url_base
        self.token = None

        if url.startswith("https") and not verify_ssl:
            self.ctx = ssl.create_default_context()
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE
        else:
            self.ctx = None

    def request(self, url, params=None, headers={}, convert=urlencode, method=None):
        request = Request(
            self.url_base + url,
            data=None if params is None else convert(params).encode("utf-8"),
            headers=headers,
            method=method
        )

        try:
            response = urlopen(request, context=self.ctx).read().decode("utf-8")
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
            params={
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

        self.request(  # no response
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
            params=realm,
            headers={
                "Authorization": "Bearer " + self.token["access_token"],
                "Content-Type": "application/json",
            },
            convert=json.dumps
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
            params=client,
            headers={
                "Authorization": "Bearer " + self.token["access_token"],
                "Content-Type": "application/json",
            },
            convert=json.dumps,
            method="PUT"
        )

    def append_list_properties(self, realm_name, client_id, additions):
        """
        Append to client list properties.

        Args:
            realm_name (str): the realm
            client_id (str): the client-id
            additions (dict): dictionary of additions, each entry's key should correspond to a client key and that
                              entry's (singular) value will be appended to the client's property.
        """
        client = self.get_client(realm_name, client_id)

        for key, value in additions.items():
            if key not in client:
                client[key] = []
            if value not in client[key]:
                client[key].append(value)

        self.update_client(realm_name, client['id'], client)

    def add_redirect_uri(self, realm_name, client_id, uri):
        self.append_list_properties(realm_name, client_id, {"redirectUris": uri})

    def get_client_installation_json(self, realm_name, client_id):
        client = self.get_client(realm_name, client_id)

        resp = self.request(
            "/auth/admin/realms/{}/clients/{}/installation/providers/keycloak-oidc-keycloak-json".format(realm_name, client["id"]),
            headers={
                "Authorization": "Bearer " + self.token["access_token"],
                "Content-Type": "application/json",
            }
        )

        return resp


class ExternalCalls:
    def __init__(self, session, keypair, domain):
        self.session = session
        self.keypair_file = keypair_to_file(keypair)
        self.bastion_hostname = "bastion." + domain
        self.bastion_ip = bastion.machine_lookup(session, self.bastion_hostname)
        self.vault_hostname = "vault." + domain
        self.vault_ip = bastion.machine_lookup(session, self.vault_hostname, public_ip=False)
        self.domain = domain
        self.ssh_target = None

    def vault_init(self):
        """ Call vault-init on the first machine and vault-unseal on all others"""
        vaults = bastion.machine_lookup_all(self.session, self.vault_hostname, public_ip=False)

        def connect(ip, func):
            bastion.connect_vault(self.keypair_file, ip, self.bastion_ip, func)

        connect(vaults[0], lambda: vault.vault_init(machine=self.vault_hostname))
        for ip in vaults[1:]:
            connect(ip, lambda: vault.vault_unseal(machine=self.vault_hostname))


    def vault(self, cmd, *args, **kwargs):
        def delegate():
            # Have to dynamically lookup the function because vault.COMMANDS
            # references the command line version of the commands we want to execute
            return vault.__dict__[cmd.replace('-', '_')](*args, machine=self.vault_hostname, **kwargs)

        return bastion.connect_vault(self.keypair_file, self.vault_ip, self.bastion_ip, delegate)

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
        self.ssh_target_ip = bastion.machine_lookup(self.session, self.ssh_target, public_ip=False)

    def ssh(self, cmd):
        if self.ssh_target is None:
            raise Exception("No SSH Target Set")

        return bastion.ssh_cmd(self.keypair_file,
                               self.ssh_target_ip,
                               self.bastion_ip,
                               cmd)

    def ssh_tunnel(self, cmd, port, local_port=None):
        """
        call to the bastion.ssh_tunnel command
        Args:
            cmd: command to run through ssh
            port: remote port to use for tunnel
            local_port: local port to use for tunnel

        Returns:
            None

        """
        if self.ssh_target is None:
            raise Exception("No SSH Target Set")

        return bastion.ssh_tunnel(self.keypair_file,
                                  self.ssh_target_ip,
                                  self.bastion_ip,
                                  port,
                                  local_port,
                                  cmd)


def vpc_id_lookup(session, vpc_domain):
    """
    Lookup the Id for the VPC with the given domain name.
    Args:
        session: amazon session
        vpc_domain: vpc to lookup

    Returns:
        id of vpc

    """
    if session is None:
        return None

    client = session.client('ec2')
    response = client.describe_vpcs(Filters=[{"Name": "tag:Name", "Values": [vpc_domain]}])
    if len(response['Vpcs']) == 0:
        return None
    else:
        return response['Vpcs'][0]['VpcId']


def subnet_id_lookup(session, subnet_domain):
    """
    Lookup the Id for the Subnet with the given domain name.
    Args:
        session: amazon session
        subnet_domain: subnet domain to look up

    Returns:
        id of the subnet domain

    """
    if session is None:
        return None

    client = session.client('ec2')
    response = client.describe_subnets(Filters=[{"Name": "tag:Name", "Values": [subnet_domain]}])
    if len(response['Subnets']) == 0:
        return None
    else:
        return response['Subnets'][0]['SubnetId']


def azs_lookup(session):
    """
    Lookup all of the Availablity Zones for the connected region.
    Args:
        session: amazon session

    Returns:
        amazon availability zones

    """
    if session is None:
        return []

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
    """
    Lookup the Id for the AMI with the given name.
    Args:
        session: amazon session
        ami_name: name of the AMI

    Returns:
        tuple of imageId and Value Tag.

    """
    if session is None:
        return None

    if ami_name.endswith(".boss"):
        ami_version = os.environ["AMI_VERSION"]
        if ami_version == "latest":
            # limit latest searching to only versions tagged with hash information
            ami_name += "-h*"
        else:
            ami_name += "-" + ami_version

    client = session.client('ec2')
    response = client.describe_images(Filters=[{"Name": "name", "Values": [ami_name]}])
    if len(response['Images']) == 0:
        return None
    else:
        response['Images'].sort(key=lambda x: x["CreationDate"], reverse=True)
        image = response['Images'][0]
        ami = image['ImageId']
        tag = _find(image.get('Tags', []), lambda x: x["Key"] == "Commit")
        commit = None if tag is None else tag["Value"]

        return (ami, commit)


def sg_lookup(session, vpc_id, group_name):
    """
    Lookup the Id for the VPC Security Group with the given name.
    Args:
        session: amazon session
        vpc_id: id of VPC containting security group
        group_name: name of security group to look up

    Returns:
        security group id of the security group with the passed in name.

    """
    if session is None:
        return None

    client = session.client('ec2')
    response = client.describe_security_groups(Filters=[{"Name": "vpc-id", "Values": [vpc_id]},
                                                        {"Name": "tag:Name", "Values": [group_name]}])

    if len(response['SecurityGroups']) == 0:
        return None
    else:
        return response['SecurityGroups'][0]['GroupId']


def rt_lookup(session, vpc_id, rt_name):
    """
    Lookup the Id for the VPC Route Table with the given name.
    Args:
        session: amazon session
        vpc_id: id of VPC to look up route table in
        rt_name: name of route table

    Returns:
        route table id for the route table with given name.

    """
    if session is None:
        return None

    client = session.client('ec2')
    response = client.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [vpc_id]},
                                                     {"Name": "tag:Name", "Values": [rt_name]}])

    if len(response['RouteTables']) == 0:
        return None
    else:
        return response['RouteTables'][0]['RouteTableId']


def rt_name_default(session, vpc_id, new_rt_name):
    """
    Find the default VPC Route Table and give it a name so that it can be referenced latter.
    Needed because by default the Route Table does not have a name and rt_lookup() will not find it.
    Args:
        session: amazon session
        vpc_id: ID of VPC
        new_rt_name: new name for default VPC Route Table

    Returns:
        None

    """
    client = session.client('ec2')
    response = client.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])
    rt_id = response['RouteTables'][0]['RouteTableId']  # TODO: verify that Tags does not already have a name tag

    resource = session.resource('ec2')
    rt = resource.RouteTable(rt_id)
    response = rt.create_tags(Tags=[{"Key": "Name", "Value": new_rt_name}])


def peering_lookup(session, from_id, to_id):
    """
    Lookup the Id for the Peering Connection between the two VPCs.
    Args:
        session: amazon session
        from_id: id of from VPC
        to_id: id of to VPC

    Returns:
        peering connection id

    """
    if session is None:
        return None

    client = session.client('ec2')
    response = client.describe_vpc_peering_connections(Filters=[{"Name": "requester-vpc-info.vpc-id",
                                                                 "Values": [from_id]},
                                                                {"Name": "requester-vpc-info.owner-id",
                                                                 "Values": ["256215146792"]},
                                                                {"Name": "accepter-vpc-info.vpc-id",
                                                                 "Values": [to_id]},
                                                                {"Name": "accepter-vpc-info.owner-id",
                                                                 "Values": ["256215146792"]},
                                                                {"Name": "status-code", "Values": ["active"]},
                                                                ])

    if len(response['VpcPeeringConnections']) == 0:
        return None
    else:
        return response['VpcPeeringConnections'][0]['VpcPeeringConnectionId']


def keypair_lookup(session):
    """
    Print the valid key pairs for the session and ask the user which to use.
    Args:
        session: amazon session

    Returns:
        valid keypair

    """
    if session is None:
        return None

    client = session.client('ec2')
    response = client.describe_key_pairs()

    # If SSH_KEY exists and points to a valid Key Pair, use it
    key = os.environ.get("SSH_KEY", None)  # reuse bastion.py env vars
    if key is not None:
        kp_name = os.path.basename(key)
        if kp_name.endswith(".pem"):
            kp_name = kp_name[:-4]
        for kp in response['KeyPairs']:
            if kp["KeyName"] == kp_name:
                return kp_name

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
        except KeyboardInterrupt:
            sys.exit(1)
        except:
            print("Invalid Key Pair number, try again")


def instanceid_lookup(session, hostname):
    """
    Look up instance id by hostname.
    Args:
        session: amazon session
        hostname: hostname to lookup

    Returns:
        InstanceId of hostname or None
    """
    if session is None:
        return None

    client = session.client('ec2')
    response = client.describe_instances(
        Filters=[{"Name": "tag:Name", "Values": [hostname]}])

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
    if session is None:
        return None

    client = session.client('acm')
    response = client.list_certificates()
    for certs in response['CertificateSummaryList']:
        if certs['DomainName'] == domain_name:
            return certs['CertificateArn']
    return None


def instance_public_lookup(session, hostname):
    """
    Look up instance id by hostname.
    Args:
        session: amazon session
        hostname: hostname to lookup

    Returns:
        (string) Public DNS name or None if it does not exist.

    """
    if session is None:
        return None

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
    """
    Look up instance id by hostname.
    Args:
        session: amazon session
        hostname: hostname to lookup

    Returns: public DNS name of elb starting with hostname.

    """
    if session is None:
        return None

    client = session.client('elb')
    responses = client.describe_load_balancers()

    hostname_ = hostname.replace(".", "-")

    for response in responses["LoadBalancerDescriptions"]:
        if response["LoadBalancerName"].startswith(hostname_):
            return response["DNSName"]
    return None


def lb_lookup(session, lb_name):
    """
    Lookup the Id for the loadbalancer with the given name.
    Args:
        session: session information used to peform lookups
        lb_name: loadbalancer name to lookup

    Returns: true if a valid loadbalancer name

    """
    if session is None:
        return None

    client = session.client('elb')
    response = client.describe_load_balancers()

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
    if session is None:
        return None

    client = session.client('sns')
    response = client.list_topics()
    topics_list = response['Topics']
    for topic in topics_list:
        arn_topic_name = topic["TopicArn"].split(':').pop()
        if arn_topic_name == topic_name:
            return topic["TopicArn"]
    return None


def request_cert(session, domain_name, validation_domain='theboss.io'):
    """
    Requests a certificate in the AWS Certificate Manager for the domain name
    Args:
        session: AWS session object used to make the request
        domain_name: domain name the certificate is being requested for
        validation_domain: domain suffix the request will be sent to.

    Returns: response from the request_certificate()

    """
    if session is None:
        return None

    client = session.client('acm')
    validation_options = [
        {
            'DomainName': domain_name,
            'ValidationDomain': validation_domain
        },
    ]
    response = client.request_certificate(DomainName=domain_name,
                                          DomainValidationOptions=validation_options)
    return response


def get_hosted_zone_id(session, hosted_zone='theboss.io'):
    """
    given a hosted zone, fine the HostedZoneId
    Args:
        session: amazon session object
        hosted_zone: the zone being hosted in route 53

    Returns:  the Id for the hosted zone or None

    """
    if session is None:
        return None

    client = session.client('route53')
    response = client.list_hosted_zones_by_name(
        DNSName=hosted_zone,
        MaxItems='1'
    )
    if len(response['HostedZones']) >= 1:
        full_id = response['HostedZones'][0]['Id']
        id_parts = full_id.split('/')
        return id_parts.pop()
    else:
        return None


def set_domain_to_dns_name(session, domain_name, dns_resource, hosted_zone='theboss.io'): # TODO move into CF config??
    """
    Sets the domain_name to use the dns name.
    Args:
        session: amazon session object
        domain_name: full domain name.  (Ex:  auth.integration.theboss.io)
        dns_resource: DNS name being assigned to this domain name  (Ex: DNS for loadbalancer)
        hosted_zone: hosted zone being managed by route 53

    Returns:  results from change_resource_record_sets

    """
    if session is None:
        return None

    client = session.client('route53')
    hosted_zone_id = get_hosted_zone_id(session, hosted_zone)

    if hosted_zone_id is None:
        print("Error: Unable to find Route 53 Hosted Zone, " + hosted_zone + ",  Cannot set resource record for: " +
              dns_resource)
        return

    response = client.change_resource_record_sets(
        HostedZoneId=hosted_zone_id,
        ChangeBatch={
            'Changes': [
                {
                    'Action': 'UPSERT',
                    'ResourceRecordSet': {
                        'Name': domain_name,
                        'Type': 'CNAME',
                        'ResourceRecords': [
                            {
                                'Value': dns_resource
                            },
                        ],
                        'TTL': 300,
                    }
                },
            ]
        }
    )
    return response

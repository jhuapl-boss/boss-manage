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

"""Library for common methods that are used by the different configs scripts.

Library currently appends the boss-manage.git/vault/ directory to the system path
so that it can import vault/bastion.py and vault/vault.py.

Library contains a set of AWS lookup methods for locating AWS data and other related
helper functions and classes.

Author:
    Derek Pryor <Derek.Pryor@jhuapl.edu>
"""

import sys
import os
import json
import pprint
import time
import getpass
import string
import subprocess
import shlex
import shutil
import tempfile
import traceback
import ssl
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError
from botocore.exceptions import ClientError

# Add a reference to boss-manage/vault/ so that we can import those files
cur_dir = os.path.dirname(os.path.realpath(__file__))
vault_dir = os.path.normpath(os.path.join(cur_dir, "..", "vault"))
sys.path.append(vault_dir)
import bastion
import vault


def zip_directory(directory, name = "lambda"):
    target = os.path.join(tempfile.mkdtemp(), name)
    return shutil.make_archive(target, "zip", directory, directory)

def json_sanitize(data):
    return (data.replace('"', '\"')
                .replace('\\', '\\\\'))

def get_commit():
    """Get the git commit hash of the current directory.

    Returns:
        (string) : The git commit hash or "unknown" if it could not be located
    """
    try:
        cmd = "git rev-parse HEAD"
        result = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE)
        return result.stdout.decode("utf-8").strip()
    except:
        return "unknown"


def domain_to_stackname(domain):
    """Convert a domain name to a CloudFormation compliant Stackname.

    Converts a domain name by removing the '.' and capitalizing each part of the domain

    Args:
        domain (string) : domain name

    Returns:
        (string) : CloudFormation stackname
    """
    return "".join(map(lambda x: x.capitalize(), domain.split(".")))


def template_argument(key, value, use_previous=False):
    """Creates a CloudFormation template formated argument.

    Converts a key value pair into a CloudFormation template formatted fragment
    (JSON formatted).

    Args:
        key (string) : CloudFormation template argument key name
        value : CloudFormation template argument value (JSON convertable)
        use_previous (bool) : Stored under the UsePreviousValue key

    Returns:
        (dict) : JSON converable dictory containing the argument
    """
    return {"ParameterKey": key, "ParameterValue": value, "UsePreviousValue": use_previous}


def keypair_to_file(keypair):
    """Looks for the SSH private key for keypair under ~/.ssh/

    Prints an error if the file doesn't exist.

    Args:
        keypair (string) : AWS keypair to locate a private key for

    Returns:
        (string|None) : SSH private key file path or None is the private key doesn't exist.
    """
    file = os.path.expanduser("~/.ssh/{}.pem".format(keypair))
    if not os.path.exists(file):
        print("Error: SSH Key '{}' does not exist".format(file))
        return None
    return file


def password(what):
    """Prompt the user for a password and verify it.

    If password and verify don't match the user is prompted again

    Args:
        what (string) : What password to enter

    Returns:
        (string) : Password
    """
    while True:
        pass_ = getpass.getpass("{} Password: ".format(what))
        pass__ = getpass.getpass("Verify {} Password: ".format(what))
        if pass_ == pass__:
            return pass_
        else:
            print("Passwords didn't match, try again.")


def generate_password(length=16):
    """Generate an alphanumeric password of the given length.

    Args:
        length (int) : length of the password to be generated

    Returns:
        (string) : password
    """
    chars = string.ascii_letters + string.digits  #+ string.punctuation
    return "".join([chars[c % len(chars)] for c in os.urandom(length)])

def delete_stack(session, domain, config):
    """Deletes the given stack from CloudFormation.

    Initiates the stack delete and waits for it to finish.  config and domain
    are combined to identify the stack.

    Args:
        session (boto3.Session): An active session.
        domain (string): Name of domain.
        config (string): Name of config.

    Returns:
        (bool) : True if stack successfully deleted.
    """
    name = domain_to_stackname(config + "." + domain)
    client = session.client("cloudformation")
    client.delete_stack(StackName = name)
    # waiter = client.get_waiter('stack_delete_complete')
    # waiter.wait(StackName = name)

    print("Waiting for delete ", end="", flush=True)

    try:
        response = client.describe_stacks(StackName = name)
        get_status = lambda r: r['Stacks'][0]['StackStatus']
        while get_status(response) == 'DELETE_IN_PROGRESS':
            time.sleep(5)
            print(".", end="", flush=True)
            response = client.describe_stacks(StackName=name)
        print(" done")

        if get_status(response) == 'DELETE_COMPLETE':
            print("Deleted stack '{}'".format(name))
            return True

        print("Status of stack '{}' is '{}'".format(name, get_status(response)))
        return False
    except ClientError as e:
        # Stack doesn't exist or no longer exists.
        print(" done")

    return True

class KeyCloakClient:
    """Client for connecting to Keycloak and using the REST API.

    Client provides a method for issuing requests to the Keycloak REST API and
    a set of methods to simplify Keycloak configuration.
    """
    def __init__(self, url_base, verify_ssl=True):
        """KeyCloakClient constructor

        Args:
            url_base (string) : The base URL to prepend to all request URLs
            verify_ssl (bool) : Whether or not to verify HTTPS certs
        """
        self.url_base = url_base
        self.token = None

        if self.url_base.startswith("https") and not verify_ssl:
            self.ctx = ssl.create_default_context()
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE
        else:
            self.ctx = None

    def request(self, url, params=None, headers={}, convert=urlencode, method=None):
        """Make a request to the Keycloak server.

        Args:
            url (string) : REST API URL to query (appended to url_base from constructor)
            params (None|dict) : None or a dict or key values that will be passed
                                 to the convert argument to produce a string
            headers (dict) : Dictionary of HTTP headers
            convert : Function to convert params into a string
                      Defaults to urlencode, taking a dict and making a url encoded string
            method (None|string) : HTTP method to use or None for the default method
                                   based on the different arguments

        Returns:
            (None) : If there is an exception raised
            (dict) : Dictionary containing JSON encoded response
        """
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
            else:
                response = {}
            return response
        except HTTPError as e:
            print("Error on '{}'".format(url))
            print(e)
            return None

    def login(self, username, password):
        """Login to the Keycloak master realm and retrieve an access token.

        WARNING: If the base_url is not using HTTPS the password will be submitted
                 in plain text over the network.

        Note: A user must be logged in before any other method calls will work

        The bearer access token is saved as self.token["access_token"]

        An error will be printed if login failed

        Args:
            username (string) : Keycloak username
            password (string) : Keycloak password
        """
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
        """Logout from Keycloak.

        Logout will invalidate the Keycloak session and clean the local token (
        self.token)
        """
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
        """Create a new realm based on the JSON based configuration.

            Note: User must be logged into Keycloak first

        Args:
            realm (dict) : JSON dictory configuration for the new realm
        """
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
        """Get the realm's client configuration.

            Note: User must be logged into Keycloak first

        Args:
            realm_name (string) : Name of the realm to look in for the client
            client_id (string) : Client ID of client configuration to retrieve

        Returns:
            (None|dict) : None if the client couldn't be located or the JSON
                          dictionary configuration of the client
        """
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

    def update_client(self, realm_name, client):
        """Update the realm's client configuration.

            Note: User must be logged into Keycloak first

        Args:
            realm_name (string) : Name of the realm
            client (dict) : JSON dictory configuration for the updated realm client
        """
        resp = self.request(
            "/auth/admin/realms/{}/clients/{}".format(realm_name, client['id']),
            params=client,
            headers={
                "Authorization": "Bearer " + self.token["access_token"],
                "Content-Type": "application/json",
            },
            convert=json.dumps,
            method="PUT"
        )

    def append_list_properties(self, realm_name, client_id, additions):
        """Append a set of key values to a realm's client configuration.

        Download the current realm's client configuration, updated with the given
        key values, and then upload the updated client configuration to the Keycloak
        server.

            Note: User must be logged into Keycloak first

        Args:
            realm_name (string) : Name of the realm
            client_id (string) : Client ID of client configuration to retrieve
            additions (dict) : dictionary of additions, each entry's key should
                               correspond to a client key and that entry's (singular)
                               value will be appended to the client's property.
        """
        client = self.get_client(realm_name, client_id)

        for key, value in additions.items():
            if key not in client:
                client[key] = []
            if value not in client[key]:
                client[key].append(value)

        self.update_client(realm_name, client)

    def add_redirect_uri(self, realm_name, client_id, uri):
        """Add the given uri as a valid redirectUri to a realm's client configuration.

            Note: User must be logged into Keycloak first

        Args:
            realm_name (string) : Name of the realm
            client_id (string) : Client ID of client configuration to retrieve
            uri (string) : URL to add to the client's list of valid redirect URLs
        """
        self.append_list_properties(realm_name, client_id, {"redirectUris": uri})

    def get_client_installation_url(self, realm_name, client_id):
        """Returns information about this client installation (suitable for wget/curl).

            Note: User must be logged into Keycloak first

        Args:
            realm_name (string) : Name of the realm
            client_id (string) : Client ID of client configuration to retrieve

        Returns:
            (dict) : contains keys
                      * 'url' for the complete URL to retrieve the client installation json
                      * 'headers' for the authorization header populated with the bearer token.
        """
        client = self.get_client(realm_name, client_id)
        installation_endpoint = "{}/auth/admin/realms/{}/clients/{}/installation/providers/keycloak-oidc-keycloak-json"\
            .format(self.url_base, realm_name, client["id"])
        auth_header = "Authorization: Bearer {}".format(self.token["access_token"])
        return {"url": installation_endpoint, "headers": auth_header}


class ExternalCalls:
    """Class that helps with forming connections from the local machine to machines
    within a VPC through the VPC's bastion machine.
    """
    def __init__(self, session, keypair, domain):
        """ExternalCalls constructor

        Args:
            session (Session) : Boto3 session used to lookup machine IPs in AWS
            keypair (string) : Name of the AWS EC2 keypair to use when connecting
                               All AWS EC2 instances connected to need to use the
                               same keypair
                               Keypair is converted to file on disk using keypair_to_file()
            domain (string) : BOSS internal VPC domain name
        """
        self.session = session
        self.keypair_file = keypair_to_file(keypair)
        self.bastion_hostname = "bastion." + domain
        self.bastion_ip = bastion.machine_lookup(session, self.bastion_hostname)
        self.vault_hostname = "vault." + domain
        self.vault_ip = bastion.machine_lookup(session, self.vault_hostname, public_ip=False)
        self.domain = domain
        self.ssh_target = None

    def vault_init(self):
        """Initialize and configure all of the vault servers.

        Lookup all vault IPs for the VPC, initialize and configure the first server
        and then unseal any other servers.
        """
        vaults = bastion.machine_lookup_all(self.session, self.vault_hostname, public_ip=False)

        def connect(ip, func):
            bastion.connect_vault(self.keypair_file, ip, self.bastion_ip, func)

        connect(vaults[0], lambda: vault.vault_init(machine=self.vault_hostname, ip=vaults[0]))
        for ip in vaults[1:]:
            connect(ip, lambda: vault.vault_unseal(machine=self.vault_hostname, ip=ip))


    def vault(self, cmd, *args, **kwargs):
        """Call the specified vault command (from vault.py) with the given arguments

        Args:
            cmd (string) : Name of the vault command to execute (name of function
                           defined in vault.py)
            args (list) : Positional arguments to pass to the vault command
            kwargs (dict) : Keyword arguments to pass to the vault command

        Returns:
            (object) : Value returned by the vault command
        """
        def delegate():
            # Have to dynamically lookup the function because vault.COMMANDS
            # references the command line version of the commands we want to execute
            return vault.__dict__[cmd.replace('-', '_')](*args, machine=self.vault_hostname, ip=self.vault_ip, **kwargs)

        return bastion.connect_vault(self.keypair_file, self.vault_ip, self.bastion_ip, delegate)

    def vault_write(self, path, **kwargs):
        """Vault vault-write with the given arguments

        WARNING: vault-write will override any data at the given path

        Args:
            path (string) : Vault path to write data to
            kwargs (dict) : Keyword key value pairs to store in Vault
        """
        self.vault("vault-write", path, **kwargs)

    def vault_update(self, path, **kwargs):
        """Vault vault-update with the given arguments

        Args:
            path (string) : Vault path to write data to
            kwargs (dict) : Keyword key value pairs to store in Vault
        """
        self.vault("vault-update", path, **kwargs)

    def vault_read(self, path):
        """Vault vault-read for the given path

        Args:
            path (string) : Vault path to read data from

        Returns:
            (None|dict) : None if no data or dictionary of key value pairs stored
                          at Vault path
        """
        res = self.vault("vault-read", path)
        return None if res is None else res['data']

    def vault_delete(self, path):
        """Vault vault-delete for the givne path

        Args:
            path (string) : Vault path to delete data from
        """
        self.vault("vault-delete", path)

    def set_ssh_target(self, target):
        """Set the target machine for the SSH commands

        Args:
            target (string) : target machine name. If the name is not fully qualified
                              it is qualified using the domain given in the constructor.
        """
        self.ssh_target = target
        if not target.endswith("." + self.domain):
            self.ssh_target += "." + self.domain
        self.ssh_target_ip = bastion.machine_lookup(self.session, self.ssh_target, public_ip=False)

    def ssh(self, cmd):
        """Execute a command over SSH on the SSH target

        Args:
            cmd (string) : Command to execute on the SSH target

        Returns:
            (None)
        """
        if self.ssh_target is None:
            raise Exception("No SSH Target Set")

        return bastion.ssh_cmd(self.keypair_file,
                               self.ssh_target_ip,
                               self.bastion_ip,
                               cmd)

    def ssh_tunnel(self, cmd, port, local_port=None):
        """Execute a function within a SSH tunnel.

        Args:
            cmd (string) : Function to execute after the tunnel is established
                           Function is passed the local port of the tunnel to use
            port (int|string) : Remote port to use for tunnel
            local_port (None|int|string : Local port to use for tunnel or None if
                                          the function should select a random port

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
    """Lookup the Id for the VPC with the given domain name.

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        vpc_domain (string) : Name of VPC to lookup

    Returns:
        (string|None) : VPC ID or None if the VPC could not be located
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
    """Lookup the Id for the Subnet with the given domain name.

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        subnet_domain (string) : Name of Subnet to lookup

    Returns:
        (string|None) : Subnet ID or None if the Subnet could not be located
    """
    if session is None:
        return None

    client = session.client('ec2')
    response = client.describe_subnets(Filters=[{"Name": "tag:Name", "Values": [subnet_domain]}])
    if len(response['Subnets']) == 0:
        return None
    else:
        return response['Subnets'][0]['SubnetId']

def multi_subnet_id_lookup(session, filters):
    """Lookup the Ids for the all Subnets that pass the filters.

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS.   If session is None no lookup is performed
        filters (list) : List of dicts specifying how to filter all the available subnets.

    Returns:
        (list) : Subnet IDs as strings.
    """
    if session is None:
        return []

    client = session.client('ec2')
    response = client.describe_subnets(Filters=filters)
    return [subnet['SubnetId'] for subnet in response['Subnets']]


def azs_lookup(session):
    """Lookup all of the Availablity Zones for the connected region.

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed

    Returns:
        (list) : List of tuples (availability zone, zone letter)
    """
    if session is None:
        return []

    client = session.client('ec2')
    response = client.describe_availability_zones()
    rtn = [(z["ZoneName"], z["ZoneName"][-1]) for z in response["AvailabilityZones"]]

    return rtn


def _find(xs, predicate):
    """Locate an item in a list based on a predicate function.

    Args:
        xs (list) : List of  data
        predicate (function) : Function taking a data item and returning bool

    Returns:
        (object|None) : The first list item that predicate returns True for or None
    """
    for x in xs:
        if predicate(x):
            return x
    return None


def ami_lookup(session, ami_name):
    """Lookup the Id for the AMI with the given name.

    If ami_name ends with '.boss', the AMI_VERSION environmental variable is used
    to either search for the latest commit hash tagged AMI ('.boss-h<hash>') or
    for the AMI with the specific tag ('.boss-<AMI_VERSION>').

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        ami_name (string) : Name of AMI to lookup

    Returns:
        (tuple|None) : Tuple of strings (AMI ID, Commit hash of AMI build) or None
                       if AMI could not be located
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
    """Lookup the Id for the VPC Security Group with the given name.

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        vpc_id (string) : VPC ID of the VPC to search in
        group_name (string) : Name of the Security Group to lookup

    Returns:
        (string|None) : Security Group ID or None if the Security Group could not be located
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
    """Lookup the Id for the VPC Route Table with the given name.

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        vpc_id (string) : VPC ID of the VPC to search in
        rt_name (string) : Name of the Route Table to lookup

    Returns:
        (string|None) : Route Table ID or None if the Route Table could not be located
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
    """Name the default Route Table that is created for a new VPC.

    Find the default VPC Route Table and give it a name so that it can be referenced latter.
    Needed because by default the Route Table does not have a name and rt_lookup() will not find it.

    The default VPC Route Table is determined as the first Route Table without a
    name.

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        vpc_id (string) : VPC ID of the VPC to search in
        new_rt_name (string) : Name to give the VPC's default Route Table

    Returns:
        None
    """
    client = session.client('ec2')
    response = client.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])

    rt_id = None
    for rt in response['RouteTables']:
        nt = _find(rt['Tags'], lambda x: x['Key'] == 'Name')
        if nt is None or nt['Value'] == '':
            rt_id = rt['RouteTableId']

    if rt_id is None:
        print("Could not locate unnamed default route table")
        return

    resource = session.resource('ec2')
    rt = resource.RouteTable(rt_id)
    response = rt.create_tags(Tags=[{"Key": "Name", "Value": new_rt_name}])


def peering_lookup(session, from_id, to_id, owner_id="256215146792"):
    """Lookup the Id for the Peering Connection between the two VPCs.

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        from_id (string) : VPC ID of the VPC from which the Peering Connection is
                           made (Requester)
        to_id (string) : VPC ID of the VPC to which the Peering Connection is made
                         (Accepter)
        owner_id (string) : Account ID that owns both of the VPCs that are connected

    Returns:
        (string|None) : Peering Connection ID or None if the Peering Connection
                        could not be located
    """
    if session is None:
        return None

    client = session.client('ec2')
    response = client.describe_vpc_peering_connections(Filters=[{"Name": "requester-vpc-info.vpc-id",
                                                                 "Values": [from_id]},
                                                                {"Name": "requester-vpc-info.owner-id",
                                                                 "Values": [owner_id]},
                                                                {"Name": "accepter-vpc-info.vpc-id",
                                                                 "Values": [to_id]},
                                                                {"Name": "accepter-vpc-info.owner-id",
                                                                 "Values": [owner_id]},
                                                                {"Name": "status-code", "Values": ["active"]},
                                                                ])

    if len(response['VpcPeeringConnections']) == 0:
        return None
    else:
        return response['VpcPeeringConnections'][0]['VpcPeeringConnectionId']


def keypair_lookup(session):
    """Lookup the names of valid Key Pair.

    If the SSH_KEY enviro variable is defined and points to a valid keypair, that
    keypair name is returned. Else all of the keypairs are printed to stdout and
    the user is prompted to select which keypair to use.

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed

    Returns:
        (string|None) : Key Pair Name or None if the session is None
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
    """Look up instance id by hostname (instance name).

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        hostname (string) : Name of the Instance to lookup

    Returns:
        (string|None) : Instance ID or None if the Instance could not be located
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
    """Looks up the ARN for a SSL Certificate

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        domain_name (string) : Domain Name that the Certificate was issued for

    Returns:
        (string|None) : Certificate ARN or None if the Certificate could not be located
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
    """Lookup the Public DNS name for a EC2 instance

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        hostname (string) : Name of the Instance to lookup

    Returns:
        (string|None) : Public DNS name or None if the Instance could not be
                        located / has no Public DNS name
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
    """Lookup the Public DNS name for a ELB

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        hostname (string) : Name of the ELB to lookup

    Returns:
        (string|None) : Public DNS name or None if the ELB could not be located
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


# Should be something more like elb_check / elb_name_check, because
# _lookup is normally used to return the ID of something
def lb_lookup(session, lb_name):
    """Look up ELB Id by name

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        lb_name (string) : Name of the ELB to lookup

    Returns:
        (bool) : If the lb_name is a valid ELB name
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
    """Lookup up SNS topic ARN given a topic name

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        topic_name (string) : Name of the topic to lookup

    Returns:
        (string|None) : ARN for the topic or None if the topic could not be located
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
    """Requests a certificate in the AWS Certificate Manager for the domain name

    Args:
        session (Session|None) : Boto3 session used to communicate with AWS CertManager
                                 If session is None no action is performed
        domain_name (string) : domain name the certificate is being requested for
        validation_domain (string) : domain suffix that request validation email
                                     will be sent to.

    Returns:
        (dict|None) : Dictionary with the "CertificateArn" key containing the new
                      certificate's ARN or None if the session is None
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
    """Look up Hosted Zone ID by DNS Name

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        hosted_zone (string) : DNS Name of the Hosted Zone to lookup

    Returns:
        (string|None) : Hosted Zone ID or None if the Hosted Zone could not be located
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
    """Look up Hosted Zone ID by DNS Name

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        domain_name (string) : FQDN of the public record to create / update
        dns_resource (string) : Public FQDN of the AWS resource to map domain_name to
        hosted_zone (string) : DNS Name of the Hosted Zone that contains domain_name

    Returns:
        (dict|None) : Dictionary with the "ChangeInfo" key containing a dict of
                      information about the requested change or None if the session
                      is None
    """
    if session is None:
        return None

    client = session.client('route53')
    hosted_zone_id = get_hosted_zone_id(session, hosted_zone)

    if hosted_zone_id is None:
        print("Error: Unable to find Route 53 Hosted Zone, " + hosted_zone + ",  Cannot set resource record for: " +
              dns_resource)
        return None

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

def route53_delete_records(session, hosted_zone, cname):
    """Delete all of the matching CNAME records from a DNS Zone

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no delete is performed
        hosted_zone (string) : Name of the hosted zone
        cname (string) : The DNS records to delete
    """
    if session is None:
        return None

    client = session.client('route53')
    hosted_zone_id = get_hosted_zone_id(session, hosted_zone)

    if hosted_zone_id is None:
        print("Could not locate Route53 Hosted Zone '{}'".format(hosted_zone))
        return None

    response = client.list_resource_record_sets(
        HostedZoneId=hosted_zone_id,
        StartRecordName=cname,
        StartRecordType='CNAME'
    )

    changes = []
    for record in response['ResourceRecordSets']:
        if not record['Name'].startswith(cname):
            continue
        changes.append({
            'Action': 'DELETE',
            'ResourceRecordSet': record
        })

    if len(changes) == 0:
        print("No {} records to remove".format(cname))
        return None

    response = client.change_resource_record_sets(
        HostedZoneId=hosted_zone_id,
        ChangeBatch={'Changes': changes}
    )
    return response

def sns_unsubscribe_all(session, topic, region="us-east-1", account="256215146792"):
    """Unsubscribe all subscriptions for the given SNS topic

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no delete is performed
        topic (string) : Name of the SNS topic
        region (string) : AWS region where SNS topic resides
        account (string) : AWS account ID
    """
    if session is None:
        return None

    topic = "arn:aws:sns:{}:{}:{}".format(region, account, topic.replace(".", "-"))

    client = session.client('sns')
    response = client.list_subscriptions()

    for res in response['Subscriptions']:
        if res['TopicArn'] == topic:
            client.unsubscribe(SubscriptionArn=res['SubscriptionArn'])

    return None

def role_arn_lookup(session, role_name):
    """
    Returns the arn associated the the role name.
    Using this method avoids hardcoding the aws account into the arn name.
    Args:
        session:
        role_name:

    Returns:

    """
    if session is None:
        return None

    client = session.client('iam')
    response = client.get_role(RoleName=role_name)
    if response is None:
        return None
    else:
        return response['Role']['Arn']

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

import os
import time
import json
import re
import sys
from boto3.session import Session

from . import constants as const
from . import hosts

def create_session(credentials):
    """Read the AWS from the credentials dictionary and then create a boto3
    connection to AWS with those credentials.
    """
    if type(credentials) == dict:
        pass
    elif type(credentials) == str:
        credentials = json.loads(credentials)
    else:
        credentials = json.load(credentials)

    session = Session(aws_access_key_id = credentials["aws_access_key"],
                      aws_secret_access_key = credentials["aws_secret_key"],
                      region_name = credentials.get('aws_region', const.REGION))
    return session

def use_iam_role():
    """Create a session with no credentials, meant to be used by internal instance
    with assumed iam role.
    """
    session = Session(region_name='us-east-1')
    return session 

def machine_lookup_all(session, hostname, public_ip = True):
    """Lookup all of the IP addresses for a given AWS instance name.

    Multiple instances with the same name is a result of instances belonging to
    an auto scale group. Useful when an action needs to happen to all machines
    in an auto scale group.

    Args:
        session (Session) : Active Boto3 session
        hostname (string) : Hostname of the EC2 instances
        public_ip (bool) : Whether or not to return public IPs or private IPs

    Returns:
        (list) : List of IP addresses
    """
    client = session.client('ec2')
    response = client.describe_instances(Filters=[{"Name":"tag:Name", "Values":[hostname]},
                                                  {"Name":"instance-state-name", "Values":["running"]}])

    addresses = []
    items = response['Reservations']
    if len(items) > 0:
        for i in items:
            item = i['Instances'][0]
            if 'PublicIpAddress' in item and public_ip:
                addresses.append(item['PublicIpAddress'])
            elif 'PrivateIpAddress' in item and not public_ip:
                addresses.append(item['PrivateIpAddress'])
    return addresses

def machine_lookup(session, hostname, public_ip = True):
    """Lookup the IP addresses for a given AWS instance name.

        Note: If not address could be located an error message is printed

    If there are multiple machines with the same hostname, to select a specific
    one, prepend the hostname with "#." where '#' is the zero based index.
        Example: 0.auth.integration.boss

    Retrieved instances are sorted by InstanceId.

    Args:
        session (Session) : Active Boto3 session
        hostname (string) : Hostname of the EC2 instance
        public_ip (bool) : Whether or not to return the public IP or private IP

    Returns:
        (string|None) : IP address or None if one could not be located.
    """

    try:
        idx, target = hostname.split('.', 1)
        idx = int(idx) # if it is not a valid number, then it is a hostname
        hostname = target
    except:
        idx = 0

    client = session.client('ec2')
    response = client.describe_instances(Filters=[{"Name":"tag:Name", "Values":[hostname]},
                                                  {"Name":"instance-state-name", "Values":["running"]}])

    item = response['Reservations']
    if len(item) == 0:
        print("Could not find IP address for '{}'".format(hostname))
        return None
    else:
        item.sort(key = lambda i: i['Instances'][0]["InstanceId"])

        if len(item) <= idx:
            print("Could not find IP address for '{}' index '{}'".format(hostname, idx))
            return None
        else:
            item = item[idx]['Instances'][0]
            if 'PublicIpAddress' in item and public_ip:
                return item['PublicIpAddress']
            elif 'PrivateIpAddress' in item and not public_ip:
                return item['PrivateIpAddress']
            else:
                print("Could not find IP address for '{}'".format(hostname))
                return None

def rds_lookup(session, hostname):
    """Lookup the public DNS for a given AWS RDS instance name.

        Note: If not address could be located an error message is printed

    Args:
        session (Session) : Active Boto3 session
        hostname (string) : Instance name of the RDS instance

    Returns:
        (string|None) : Public DNS or None if one could not be located.
    """

    client = session.client('rds')
    response = client.describe_db_instances(DBInstanceIdentifier=hostname)

    item = response['DBInstances']
    if len(item) == 0:
        print("Could not find DNS for '{}'".format(hostname))
        return None
    else:
        return item[0]['Endpoint']['Address']


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


def asg_restart(session, hostname, timeout, callback=None):
    """Terminate all of the instances for an ASG, with the given timeout between
    each termination.
    """
    client = session.client('ec2')
    resource = session.resource('ec2')
    response = client.describe_instances(Filters=[{"Name":"tag:Name", "Values":[hostname]},
                                                  {"Name":"instance-state-name", "Values":["running"]}])

    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            id = instance['InstanceId']
            print("Terminating {} instance {}".format(hostname, id))
            resource.Instance(id).terminate()
            print("Sleeping for {} minutes".format(timeout/60.0))
            time.sleep(timeout)

            if callback is not None:
                callback()

def asg_name_lookup(session, hostname):
    """Lookup the Group name for the ASG creating the EC2 instances with the given hostname

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        hostname (string) : Hostname of the EC2 instances created by the ASG

    Returns:
        (string|None) : ASG Group name or None of the ASG could not be located
    """
    if session is None:
        return None

    client = session.client('autoscaling')
    response = client.describe_auto_scaling_groups()
    if len(response['AutoScalingGroups']) == 0:
        return None
    else:
        # DP NOTE: Unfortunatly describe_auto_scaling_groups() doesn't allow filtering results
        for g in response['AutoScalingGroups']:
            t = _find(g['Tags'], lambda x: x['Key'] == 'Name')
            if t and t['Value'] == hostname:
                return g['AutoScalingGroupName']
        return None

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

def azs_lookup(session, lambda_compatible_only=False):
    """Lookup all of the Availablity Zones for the connected region.

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        lambda_compatible_only(bool): only return AZs that work with Lambda.
    Returns:
        (list) : List of tuples (availability zone, zone letter)
    """
    if session is None:
        return []

    client = session.client('ec2')
    response = client.describe_availability_zones()
    # SH Removing Hack as subnet A is already in Production and causes issues trying to delete
    #    We will strip out subnets A and C when creating the lambdas.
    #rtn = [(z["ZoneName"], z["ZoneName"][-1]) for z in response["AvailabilityZones"] if z['ZoneName'] != 'us-east-1a']
    rtn = [(z["ZoneName"], z["ZoneName"][-1]) for z in response["AvailabilityZones"]]

    if lambda_compatible_only:
        current_account = get_account_id_from_session(session)
        for az in rtn.copy():
            if az[1] == 'c' and current_account == hosts.PROD_ACCOUNT:
                rtn.remove(az)
            if az[1] == 'a' and current_account == hosts.DEV_ACCOUNT:
                rtn.remove(az)
    return rtn

def ami_lookup(session, ami_name, version = None):
    """Lookup the Id for the AMI with the given name.

    If ami_name ends with '.boss', the AMI_VERSION environmental variable is used
    to either search for the latest commit hash tagged AMI ('.boss-h<hash>') or
    for the AMI with the specific tag ('.boss-<AMI_VERSION>').

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        ami_name (string) : Name of AMI to lookup
        version (string|None) : Overrides the AMI_VERSION environment variable
                                used to specify a specific version of an AMI

    Returns:
        (tuple|None) : Tuple of strings (AMI ID, Commit hash of AMI build) or None
                       if AMI could not be located
    """
    if session is None:
        return None

    specific = False
    if ami_name.endswith(".boss"):
        ami_version = os.environ["AMI_VERSION"] if version is None else version
        if ami_version == "latest":
            # limit latest searching to only versions tagged with hash information
            ami_search = ami_name + "-h*"
        else:
            ami_search = ami_name + "-" + ami_version
            specific = True
    else:
        ami_search = ami_name

    client = session.client('ec2')
    response = client.describe_images(Filters=[{"Name": "name", "Values": [ami_search]}])
    if len(response['Images']) == 0:
        if specific:
            print("Could not locate AMI '{}', trying to find the latest '{}' AMI".format(ami_search, ami_name))
            return ami_lookup(session, ami_name, version = "latest")
        else:
            return None
    else:
        response['Images'].sort(key=lambda x: x["CreationDate"], reverse=True)
        image = response['Images'][0]
        ami = image['ImageId']
        tag = _find(image.get('Tags', []), lambda x: x["Key"] == "Commit")
        commit = None if tag is None else tag["Value"]

        return (ami, commit)

class NoneDict(dict):
    """Custom Dictionary that returns none if the key doesn't exist.

    Normal behavior it to throw an exception.
    """
    def __getitem__(self, key):
        if key not in self:
            return None
        else:
            return super().__getitem__(key)

def sg_lookup_all(session, vpc_id):
    """Lookup the Ids for all of the VPC Security Groups.

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        vpc_id (string) : VPC ID of the VPC to search in

    Returns:
        (dict|None) : Dictionary of Security Group Name and ID
                      Dictionary will be empty if session is None or no security groups
                      could be located
    """
    if session is None:
        return NoneDict()

    client = session.client('ec2')
    response = client.describe_security_groups(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}])

    if len(response['SecurityGroups']) == 0:
        return NoneDict()
    else:
        sgs = NoneDict()
        for sg in response['SecurityGroups']:
            key = _find(sg.get('Tags', []), lambda x: x["Key"] == "Name")
            if key:
                key = key['Value']
            sgs[key] = sg['GroupId']

        return sgs

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


def peering_lookup(session, from_id, to_id, owner_id=None):
    """Lookup the Id for the Peering Connection between the two VPCs.

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        from_id (string) : VPC ID of the VPC from which the Peering Connection is
                           made (Requester)
        to_id (string) : VPC ID of the VPC to which the Peering Connection is made
                         (Accepter)
        owner_id (string) : Account ID that owns both of the VPCs that are connected.
                            If None is provided the Account ID will be looked up from
                            the session.

    Returns:
        (string|None) : Peering Connection ID or None if the Peering Connection
                        could not be located
    """
    if session is None:
        return None

    if owner_id is None:
        owner_id = get_account_id_from_session(session)

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
        if certs['DomainName'].startswith('*'):    # if it is a wildcard domain like "*.thebossdev.io"
            cert_name = certs['DomainName'][1:] + '$'
            if re.search(cert_name, domain_name) != None:
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


def cloudfront_public_lookup(session, hostname):
    """
    Lookup cloudfront public domain name which has hostname as the origin.
    Args:
        session(Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed
        hostname: name of api domain or auth domain. Ex: api.integration.theboss.io

    Returns:
        (string|None) : Public DNS name of cloud front or None if it could not be located
    """
    if session is None:
        return None

    client = session.client('cloudfront')
    response = client.list_distributions(
        MaxItems='100'
    )
    items = response["DistributionList"]["Items"]
    for item in items:
        cloud_front_domain_name = item["DomainName"]
        if item["Aliases"]["Quantity"] > 0:
            if hostname in item["Aliases"]["Items"]:
                return cloud_front_domain_name
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

    lb_name = lb_name.replace('.', '-')

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


def sqs_delete_all(session, domain):
    """Delete all of the SQS Queues that start with the given domain name

    Args:
        session (Session) : Boto3 session used to lookup information in AWS
        domain (string) : Domain name prefix of queues to delete

    Raises:
        (boto3.ClientError): If queue not found.
    """
    client = session.client('sqs')
    resp = client.list_queues(QueueNamePrefix=domain.replace('.','-'))

    for url in resp.get('QueueUrls', []):
        client.delete_queue(QueueUrl=url)

def sqs_lookup_url(session, queue_name):
    """Lookup up SQS url given a name.

    Args:
        session (Session) : Boto3 session used to lookup information in AWS.
        queue_name (string) : Name of the queue to lookup.

    Returns:
        (string) : URL for the queue.

    Raises:
        (boto3.ClientError): If queue not found.
    """
    client = session.client('sqs')
    resp = client.get_queue_url(QueueName=queue_name)
    return resp['QueueUrl']

def request_cert(session, domain_name, validation_domain):
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

def get_hosted_zone(session):
    """
    Get hosted zone by looking up account name and using that to tell which
     zone to return.
    Args:
        session: Boto3 Session

    Returns:
        Hosted zone name.
    """
    account = get_account_id_from_session(session)
    if account == hosts.PROD_ACCOUNT:
        return hosts.PROD_DOMAIN
    elif account == hosts.DEV_ACCOUNT:
        return hosts.DEV_DOMAIN
    else:
        return None

def get_hosted_zone_id(session, hosted_zone):
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

def set_domain_to_dns_name(session, domain_name, dns_resource, hosted_zone):
    """Updates or Creates a domain name with FQDN resource.

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


def get_dns_resource_for_domain_name(session, domain_name, dns_resource, hosted_zone):
    """gets to resource name attached to a domain name

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

def sns_unsubscribe_all(session, topic, region="us-east-1", account=None):
    """Unsubscribe all subscriptions for the given SNS topic

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no delete is performed
        topic (string) : Name of the SNS topic
        region (string) : AWS region where SNS topic resides
        account (string) : AWS account ID.  If None is provided the account ID
                           will be looked up from the session object using iam
    """
    if session is None:
        return None

    if account is None:
        account = get_account_id_from_session(session)

    topic = "arn:aws:sns:{}:{}:{}".format(region, account, topic.replace(".", "-"))

    client = session.client('sns')
    response = client.list_subscriptions()

    for res in response['Subscriptions']:
        if res['TopicArn'] == topic:
            client.unsubscribe(SubscriptionArn=res['SubscriptionArn'])

    return None


def sns_create_topic(session, topic):
    """
        Creates a new Topic
    Args:
        session:
        topic:

    Returns:
         TopicArn or None
    """
    if session is None:
        return None

    client = session.client("sns")
    response = client.create_topic(Name=topic)
    print(response)
    if response is None:
        return None
    else:
        return response['TopicArn']

def policy_delete_all(session, domain, path="/"):
    """Delete all of the IAM policies that start with the given domain name

    Args:
        session (Session) : Boto3 session used to lookup information in AWS
        domain (string) : Domain name prefix of policies to delete
        path (string) : IAM path of the policy, if one was used

    Raises:
        (boto3.ClientError): If queue not found.
    """
    client = session.client('iam')
    resp = client.list_policies(Scope='Local', PathPrefix=path)

    prefix = domain.replace('.', '-')
    for policy in resp.get('Policies', []):
        if policy['PolicyName'].startswith(prefix):
            ARN = policy['Arn']
            if policy['AttachmentCount'] > 0:
                # cannot delete a policy if it is still in use
                attached = client.list_entities_for_policy(PolicyArn=ARN)
                for group in attached.get('PolicyGroups', []):
                    client.detach_group_policy(GroupName=group['GroupName'], PolicyArn=ARN)
                for user in attached.get('PolicyUsers', []):
                    client.detach_user_policy(UserName=user['UserName'], PolicyArn=ARN)
                for role in attached.get('PolicyRoles', []):
                    client.detach_role_policy(RoleName=role['RoleName'], PolicyArn=ARN)
            client.delete_policy(PolicyArn=ARN)

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

def instance_profile_arn_lookup(session, instance_profile_name):
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
    response = client.get_instance_profile(InstanceProfileName=instance_profile_name)
    if response is None:
        return None
    else:
        return response['InstanceProfile']['Arn']


def s3_bucket_exists(session, name):
    """Test for existence of an S3 bucket.

    Note that this method can only test for the existence of buckets owned by
    the user.

    Args:
        session (Session): Boto3 session used to lookup information in AWS.
        name (string): Name of S3 bucket.

    Returns:
        (bool): True if bucket exists.
    """
    client = session.client('s3')
    resp = client.list_buckets()
    for bucket in resp['Buckets']:
        if bucket['Name'] == name:
            return True

    return False

def get_account_id_from_session(session):
    """
    gets the account id from the session using the iam client.  This method will work even
    if you have assumed a role in another account.
    Args:
        session (Session): Boto3 session used to lookup information in AWS.
    Returns:
        (str) AWS account id
    """

    if session is None:
        return None

    return session.client('iam').list_users(MaxItems=1)["Users"][0]["Arn"].split(':')[4]

# DP TODO: refactor all lambda server functions into some common entity so it is easy to handle multiple accounts
def get_lambda_s3_bucket(session):
    '''
    returns the lambda bucket based on the session
    Args:
        session:

    Returns:
        (str) bucket name to store lambdas
    '''
    account = get_account_id_from_session(session)
    if account == hosts.PROD_ACCOUNT:
        return hosts.PROD_LAMBDA_BUCKET
    elif account == hosts.DEV_ACCOUNT:
        return hosts.DEV_LAMBDA_BUCKET
    else:
        raise NameError("Unknown session account used, {}, S3_BUCKET for Lambda unknown.".format(account))

def get_lambda_server(session):
    '''
    returns the lambda server based on the session
    Args:
        session:

    Returns:
        (str) build server for lambdas
    '''
    account = get_account_id_from_session(session)
    if account == hosts.PROD_ACCOUNT:
        return hosts.PROD_LAMBDA_SERVER
    elif account == hosts.DEV_ACCOUNT:
        return hosts.DEV_LAMBDA_SERVER
    else:
        raise NameError("Unknown session account used, {}, lambda_build_server for this session is unknown.".format(account))

def get_lambda_server_key(session):
    '''
    returns the lambda server based on the session
    Args:
        session:

    Returns:
        (str) build server for lambdas
    '''
    account = get_account_id_from_session(session)
    if account == hosts.PROD_ACCOUNT:
        return const.PROD_LAMBDA_KEY
    elif account == hosts.DEV_ACCOUNT:
        return const.DEV_LAMBDA_KEY
    else:
        raise NameError("Unknown session account used, {}, lambda_build_server for this session is unknown.".format(account))


def lambda_arn_lookup(session, lambda_name):
    """
    Returns the arn for a lambda given a lambda function name.
    Args:
        session (Session): boto3.session.Session object
        lambda_name (str): name of the lambda function

    Returns:
        (str):
    """
    if session is None:
        return None

    client = session.client("lambda")
    response = client.get_function(FunctionName=lambda_name)
    if response is None:
        return None
    else:
        return response['Configuration']['FunctionArn']




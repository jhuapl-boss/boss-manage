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

from __future__ import print_function

from datetime import datetime
from urllib2 import urlopen
import json
import boto3

PROTOCOL = 'http://'
PORT = ':8500'
ENDPOINT = '/v1/health/node/'

NORMAL_ROUTE53_WEIGHT = 1
SICK_ROUTE53_WEIGHT = 0

def lambda_handler(event, context):
    """Entry point to AWS lambda function.

    Args:
        event (dict): Expected keys: vpc_id, vpc_name, topic_arn
        context (Context): Unused.
    """
    vpc_id = event['vpc_id']
    vpc_name = event['vpc_name']
    topic_arn = event['topic_arn']

    ec2_client = boto3.client('ec2')
    resp = ec2_client.describe_instances(Filters=[
            {
                'Name': 'tag:Name',
                'Values': ['consul*']
            },
            {
                'Name': 'vpc-id',
                'Values': [vpc_id]
            }
        ])

    sns_client = boto3.client('sns')
    route53_client = boto3.client('route53')

    if len(resp['Reservations']) == 0:
        print('No consul instances found!')
        sns_publish_no_consuls(sns_client, topic_arn, vpc_name)

    for reserv in resp['Reservations']:

        for inst in reserv['Instances']:
            ip = inst['PrivateIpAddress']
            try:
                node_id = get_node_id(ip)
            except:
                print('Could not construct node id from ip: {}'.format(ip))
                continue

            url = PROTOCOL + ip + PORT + ENDPOINT + node_id
            print('Checking consul server {} at {}...'.format(url, str(datetime.now())))

            try:
                raw = urlopen(url, timeout=4).read()
            except:
                raw = 'Error connecting to consul HTTP endpoint.'
            else:
                if validate(raw):
                    # Set weight in Route53 to default to ensure it receives
                    # traffic, normally.
                    update_route53_weight(
                        route53_client, vpc_name, inst, NORMAL_ROUTE53_WEIGHT)
                    continue

            # Health check failed.
            print(raw)

            # Publish failure to SNS topic.
            sns_publish_sick(sns_client, inst, raw, topic_arn, vpc_name)

            # Set weight in Route53 to 0 so instance gets no traffic.
            update_route53_weight(
                route53_client, vpc_name, inst, SICK_ROUTE53_WEIGHT)

def get_node_id(ip):
    """A consul's node id is derived from the last two octets of its ip.

    Args:
        ip (string): Instance's ip address.

    Returns:
        (string): Node id as known to Consul cluster.
    """
    octets = ip.split('.')
    return octets[2] + octets[3]

def validate(resp):
    """Check health status response from application.

    Args:
        resp (string): Response will be converted to JSON and then analyzed.

    Returns:
        (bool): True if application healthy.
    """
    print(resp)
    try:
        data = json.loads(resp)
    except:
        return False

    if len(data) == 0:
        return False

    for service in data:
        if service['CheckID'] == 'serfHealth':
            if service['Status'] == 'passing':
                return True

    return False

def where(xs, predicate):
    """Filter list using given function.

    Note, only the first element that passes the predicate is returned.

    Args:
        xs (list): List to filter.
        predicate (function): Function to filter by.

    Returns:
        (string|None): Returns first element that passes predicate.
    """
    for x in xs:
        if predicate(x):
            return x
    return None

def find_name(xs):
    """Search list of tags for the one with Name as its key.

    Args:
        xs (list): List of dicts as returned by Boto3's describe_instances().

    Returns:
        (string|None)
    """
    tag = where(xs, lambda x: x['Key'] == 'Name')
    return None if tag is None else tag['Value']

def sns_publish_no_consuls(sns_client, topic_arn, vpc_name):
    """Send notification of NO existing consul instances.

    Args:
        sns_client (boto3.SNS.Client): Client for interacting with SNS.
        topic_arn (string): ARN of SNS topic to publish to.
        vpc_name (string): Name of VPC.
    """
    sns_client.publish(
        TopicArn=topic_arn,
        Subject='No consul instances!',
        Message='No consul instances found in {}!'.format(vpc_name)
    )

def sns_publish_sick(sns_client, inst_data, raw_err, topic_arn, domain_name):
    """Send notification of failed instance to SNS topic.

    Args:
        sns_client (boto3.SNS.Client): Client for interacting with SNS.
        inst_data (dict): Instance info as returned by describe_instances().
        raw_err (string): Raw response from urlopen() or 'unreachable'.
        topic_arn (string): ARN of SNS topic to publish to.
        domain_name (string): Domain name of VPC.
    """
    inst_id = inst_data['InstanceId']
    sns_client.publish(
        TopicArn=topic_arn,
        Subject='consul instance not healthy',
        Message="""consul instance id {0} is failing its health check.
Raw health check: {1}

It's possible that this is a new consul instance that's initializing.
""".format(inst_id, raw_err)
    )

def update_route53_weight(route53_client, vpc_name, inst_data, weight):
    """Change weight for given instance in Route53 (DNS).

    Args:
        route53_client (boto3.Route53.Client): Client for interacting with Route53.
        vpc_name: Name of VPC instance runs in.
        inst_data (dict): Instance info as returned by describe_instances().
        weight (int): New weight for instance.
    """
    zones_resp = route53_client.list_hosted_zones_by_name(
        DNSName=vpc_name, MaxItems='1')
    zone_id = zones_resp['HostedZones'][0]['Id'].split('/')[-1]
    inst_id = inst_data['InstanceId']
    dns_name = find_name(inst_data['Tags'])
    private_dns_name = inst_data['PrivateDnsName']
    route53_client.change_resource_record_sets(
        HostedZoneId=zone_id,
        ChangeBatch = {
            'Changes': [{
                'Action': 'UPSERT',
                'ResourceRecordSet': {
                    'Name': dns_name,
                    'Type': 'CNAME',
                    'ResourceRecords': [{'Value': private_dns_name}],
                    'TTL': 300,
                    'SetIdentifier': inst_id,
                    'Weight': weight
                }
            }]
        }
    )

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

# Yes, max number of consul instances to retrieve from Route53 _should_ be a
# string!
MAX_CONSUL_INSTANCES = '20'

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

    sns_client = boto3.client('sns')
    route53_client = boto3.client('route53')

    zones = route53_client.list_hosted_zones_by_name(
        DNSName=vpc_name, MaxItems='1')
    if 'HostedZones' not in zones:
        msg = 'Invalid response from Route53 - no HostedZones!'
        sns_publish_no_consuls(sns_client, topic_arn, msg)
        print(msg)
        return

    zone_id = None
    for zone in zones['HostedZones']:
        # Route53 looks like it ends the name with a trailing period.
        if zone['Name'].startswith(vpc_name):
            zone_id = zone['Id']
            break

    if zone_id is None:
        msg = '{} not found in Route53!'.format(vpc_name)
        sns_publish_no_consuls(sns_client, topic_arn, msg)
        print(msg)
        return

    dns_name = 'consul.' + vpc_name

    hosts = route53_client.list_resource_record_sets(
        HostedZoneId=zone_id,
        StartRecordName=dns_name,
        StartRecordType='CNAME',
        MaxItems=MAX_CONSUL_INSTANCES)

    if 'ResourceRecordSets' not in hosts or len(hosts['ResourceRecordSets']) < 1:
        msg = 'Invalid response from Route53 - no ResourceRecordSets!'
        sns_publish_no_consuls(sns_client, topic_arn, msg)
        print(msg)
        return

    for record_set in hosts['ResourceRecordSets']:
        if len(record_set['ResourceRecords']) < 1:
            print('No ResourceRecords found.')
            continue

        if not record_set['Name'].startswith(dns_name):
            # No more records for consul.
            break

        inst_id = record_set['SetIdentifier']
        hostname = record_set['ResourceRecords'][0]['Value']
        try:
            ip = get_ip_from_host_name(hostname)
            node_id = get_node_id(ip)
        except:
            print('Could not construct node id from ip: {}'.format(ip))
            continue

        url = PROTOCOL + ip + PORT + ENDPOINT + node_id
        print('Checking consul server {} at {}...'.format(url, str(datetime.now())))

        try:
            raw = urlopen(url, timeout=10).read()
        except:
            raw = 'Error connecting to consul HTTP endpoint.'
        else:
            if validate(raw):
                # Set weight in Route53 to default to ensure it receives
                # traffic, normally.
                update_route53_weight(
                    route53_client, zone_id, dns_name, hostname, inst_id, NORMAL_ROUTE53_WEIGHT)
                continue

        # Health check failed.
        print(raw)

        # Publish failure to SNS topic.
        sns_publish_sick(sns_client, ip, raw, topic_arn)

        # Set weight in Route53 to 0 so instance gets no traffic.
        update_route53_weight(
            route53_client, zone_id, dns_name, hostname, inst_id, SICK_ROUTE53_WEIGHT)

def get_ip_from_host_name(name):
    """Extract ip from host name.

    Host name is in this form: ip-xxx-xxx-xxx-xxx.ec2.internal

    Args:
        name (string): Host name.

    Returns:
        (string): ip address in xxx.xxx.xxx.xxx form.
    """
    parts = name.split('-')
    last_octet = parts[4].split('.')[0]
    ip = parts[1] + '.' + parts[2] + '.' + parts[3] + '.' + last_octet
    return ip

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

def sns_publish_no_consuls(sns_client, topic_arn, msg):
    """Send notification of NO existing consul instances.

    Args:
        sns_client (boto3.SNS.Client): Client for interacting with SNS.
        topic_arn (string): ARN of SNS topic to publish to.
        vpc_name (string): Name of VPC.
    """
    sns_client.publish(
        TopicArn=topic_arn,
        Subject='No consul instances!',
        Message=msg
    )

def sns_publish_sick(sns_client, ip, raw_err, topic_arn):
    """Send notification of failed instance to SNS topic.

    Args:
        sns_client (boto3.SNS.Client): Client for interacting with SNS.
        ip (string): IP address of sick instance.
        raw_err (string): Raw response from urlopen() or 'unreachable'.
        topic_arn (string): ARN of SNS topic to publish to.
    """
    sns_client.publish(
        TopicArn=topic_arn,
        Subject='consul instance not healthy',
        Message="""consul instance with ip: {0} is failing its health check.
Raw health check: {1}
""".format(ip, raw_err)
    )

def update_route53_weight(route53_client, zone_id, dns_name, private_dns_name, inst_id, weight):
    """Change weight for given instance in Route53 (DNS).

    Args:
        route53_client (boto3.Route53.Client): Client for interacting with Route53.
        zone_id (string): Id of hosted zone.
        dns_name (string): "Public" DNS name of consul instance.
        private_dns_name (string): Internal DNS name of consul instance as known to Route53.
        inst_id (dict): EC2 instance ID.
        weight (int): New weight for instance.
    """
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

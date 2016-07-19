from __future__ import print_function

from datetime import datetime
from urllib2 import urlopen
import json
import boto3

PROTOCOL = 'http://'
PORT = ':8200'
ENDPOINT = '/v1/sys/health'
# SNS_TOPIC_ARN = 'arn:aws:sns:us-east-1:256215146792:gion-test'


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
                'Values': ['vault*']
            },
            {
                'Name': 'vpc-id',
                'Values': [vpc_id]
            }
        ])

    sns_client = boto3.client('sns')
    route53_client = boto3.client('route53')

    for reserv in resp['Reservations']:
        for inst in reserv['Instances']:
            ip = inst['PrivateIpAddress']
            url = PROTOCOL + ip + PORT + ENDPOINT
            print('Checking vault server {} at {}...'.format(url, str(datetime.now())))

            try:
                raw = urlopen(url, timeout=1).read()
            except:
                raw = 'unreachable'
            else:
                if validate(raw):
                    continue

            # Health check failed.
            # Publish failure to SNS topic.
            sns_publish(sns_client, inst, raw, topic_arn)

            # Set weight in Route53 to 0 so instance gets no traffic.
            update_route53_weight(route53_client, vpc_name, inst, 0)

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

    if 'initialized' not in data:
        return False
    if 'sealed' not in data:
        return False

    if not data['initialized'] or data['sealed']:
        return False

    return True

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

def sns_publish(sns_client, inst_data, raw_err, topic_arn):
    """Send notification of failed instance to SNS topic.

    Args:
        sns_client (boto3.SNS.Client): Client for interacting with SNS.
        inst_data (dict): Instance info as returned by describe_instances().
        raw_err (string): Raw response from urlopen() or 'unreachable'.
        topic_arn (string): ARN of SNS topic to publish to.
    """
    inst_id = inst_data['InstanceId']
    sns_client.publish(
        TopicArn=topic_arn,
        Subject='vault instance sealed',
        Message="""Vault instance id {} is uninitialized, sealed, or unreachable.
        Raw health check: {}
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

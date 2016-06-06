import json
import boto3

# NOTE: Currently only works on AutoScale notifications, if an instances is manually
#       terminated the DNS record will not be deleted.

def where(xs, predicate):
    for x in xs:
        if predicate(x):
            return x
    return None

def find_name(xs):
    tag = where(xs, lambda x: x['Key'] == "Name")
    return None if tag is None else tag['Value']

def handler(event, context):
    for record in event['Records']:
        msg = json.loads(record['Sns']['Message'])

        action = msg['Event']
        if action == "autoscaling:TEST_NOTIFICATION":
            print("Test test, this is a test")
            return

        instance_id = msg['EC2InstanceId']
        subnet_id = msg['Details']['Subnet ID']
        print("Event {} on instance {}".format(action, instance_id))

        compute = boto3.client('ec2')
        dns = boto3.client('route53')

        response = compute.describe_subnets(SubnetIds=[subnet_id])
        vpc_id = response['Subnets'][0]['VpcId']
        response = compute.describe_vpcs(VpcIds=[vpc_id])
        vpc_name = find_name(response['Vpcs'][0]['Tags'])

        response = dns.list_hosted_zones_by_name(DNSName=vpc_name, MaxItems='1')
        zone_id = response['HostedZones'][0]['Id'].split('/')[-1]

        response = compute.describe_instances(InstanceIds=[instance_id])
        instance = response['Reservations'][0]['Instances'][0]
        dns_name = find_name(instance['Tags'])

        if action in ('autoscaling:EC2_INSTANCE_LAUNCH', ):
            hostname = instance['PrivateDnsName']

            print("Map {} to {} in VPC {}".format(dns_name, hostname, vpc_name))

            dns.change_resource_record_sets(
                HostedZoneId = zone_id,
                ChangeBatch = {
                    'Changes': [{
                        'Action': 'CREATE',
                        'ResourceRecordSet': {
                            'Name': dns_name,
                            'Type': 'CNAME',
                            'ResourceRecords': [{'Value': hostname}],
                            'TTL': 300,
                            'SetIdentifier': instance_id,
                            'Weight': 0,
                        }
                    }]
                }
            )
        elif action in ('autoscaling:EC2_INSTANCE_TERMINATE', 'autoscaling:EC2_INSTANCE_LAUNCH_ERROR'):
            # Have to lookup the record based on instance_id because after delete, PrivateDnsName is empty
            response = dns.list_resource_record_sets(
                HostedZoneId=zone_id,
                StartRecordName=dns_name,
                StartRecordType='CNAME'
            )

            record = where(response['ResourceRecordSets'], lambda x: x['SetIdentifier'] == instance_id)

            dns.change_resource_record_sets(
                HostedZoneId=zone_id,
                ChangeBatch = {
                    'Changes': [{
                        'Action': 'DELETE',
                        'ResourceRecordSet': record
                    }]
                }
            )
        else:
            print("Unsupported event '{}'".format(action))
            return

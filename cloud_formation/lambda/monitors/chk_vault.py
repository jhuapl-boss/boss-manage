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
from urllib2 import urlopen, HTTPError
import json
import boto3

PROTOCOL = 'http://'
PORT = ':8200'
ENDPOINT = '/v1/sys/health'

def lambda_handler(event, context):
    """Entry point to AWS lambda function.

    Args:
        event (dict): Expected keys: vpc_id, vpc_name, topic_arn
        context (Context): Unused.
    """
    hostname = event['hostname']

    asg_client = boto3.client('autoscaling')
    ec2_client = boto3.client('ec2')
    resp = ec2_client.describe_instances(Filters=[
            {
                'Name': 'tag:Name',
                'Values': [hostname]
            },
            {
                'Name': 'instance-state-name',
                'Values': ['running']
            },
        ])

    for reserv in resp['Reservations']:
        for inst in reserv['Instances']:
            try:
                ip = inst['PrivateIpAddress']
            except KeyError:
                print("Could not locate IP Address for {} ({})".format(hostname, inst['InstanceId']))
                continue

            url = PROTOCOL + ip + PORT + ENDPOINT
            print('Checking vault server {} at {}...'.format(url, str(datetime.now())))

            try:
                raw = urlopen(url, timeout=10).read()
            except HTTPError as err:
                if err.getcode() == 500:
                    # Vault returns a status code of 500 if sealed or not
                    # initialized.
                    print('Vault sealed or uninitialized.')
                    continue
                elif err.getcode() == 429:
                    # Vault returns 429 if it's unsealed and in standby mode.
                    # This is not an error condition.
                    print('Unsealed and in standby mode.')
                    continue
                else:
                    raw = 'Status code: {}, reason: {}'.format(
                        err.getcode(), err.reason)
            except:
                raw = 'Unknown error.'
            else:
                if validate(raw):
                    # Up and working
                    continue

            # Health check failed.
            print(raw)

            # Set to unhealthy and the ASG will terminate and recreate
            asg_client.set_instance_health(InstanceId = inst['InstanceId'],
                                           HealthStatus = 'Unhealthy',
                                           ShouldRespectGracePeriod = True)

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

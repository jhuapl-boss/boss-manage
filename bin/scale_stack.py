#!/usr/bin/env python3

# Copyright 2021 The Johns Hopkins University Applied Physics Laboratory
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

"""
Simple script to scale up/down ASG. 
DO NOT USE ON PRODUCTION. 

Order of scaling up:
    bastion 
    vault 
    activities
    endpoint
    cachemanager

Order of scaling down:
    cachemanager
    endpoint
    activities
    vault
    bastion
"""

import boto3
import time
import alter_path
from botocore.exceptions import ClientError
from lib import configuration

PRODUCTION = ["bossdb.boss"]

def scale_stack(args):
    if args.bosslet_name in PRODUCTION:
        print("ERROR: Cannot scale down production environment.")
        return
    
    session = args.bosslet_config.session
    
    ### Get instance ids and ASG ids 

    ## EC2 Instances
    instances = (f"cachemanager.{args.bosslet_name}", f"bastion.{args.bosslet_name}")
    ec2_client = session.client('ec2')
    if not args.asg_only:
        instance_ids = {x: get_instance_id(ec2_client, x) for x in instances}

    ## AutoScalingGroups
    asg_client = session.client('autoscaling')
    response = asg_client.describe_auto_scaling_groups()['AutoScalingGroups']
    
    # Filter those that belong to bosslet
    bosslet_id = args.bosslet_name.split('.')[0].lower()
    bosslet_asg = {}
    for asg in response:
        if bosslet_id in asg['AutoScalingGroupName'].lower() and 'auth' not in asg['AutoScalingGroupName'].lower():
            key = asg['AutoScalingGroupName'].split('-')[1].lower()
            bosslet_asg[key] = asg['AutoScalingGroupName']

            # Check if any of the ASGs have suspended processes. Abort if they do.
            if asg['SuspendedProcesses']:
                raise Exception(f"Suspended Processes set for ASG {asg['AutoScalingGroupName']}. Aborting.")

    if args.mode == 'up':
        print("Starting bastion")
        if not args.asg_only:
            ec2_client.start_instances(InstanceIds=[instance_ids[f"bastion.{args.bosslet_name}"]])
            time.sleep(1)

        print("Waiting for bastion to initialize")
        wait_for_instance(ec2_client, f"bastion.{args.bosslet_name}")

        print("Scaling up vault")
        asg_client.update_auto_scaling_group(AutoScalingGroupName=bosslet_asg['vault'], MinSize=1, MaxSize=1, DesiredCapacity=1)
        time.sleep(1)

        print("Waiting for vault to initialize")
        wait_for_instance(ec2_client, f"vault.{args.bosslet_name}")

        print("Scaling up endpoint") 
        asg_client.update_auto_scaling_group(AutoScalingGroupName=bosslet_asg['endpoint'], MinSize=1, MaxSize=1, DesiredCapacity=1)
        time.sleep(1)
        
        print("Scaling up activities")
        asg_client.update_auto_scaling_group(AutoScalingGroupName=bosslet_asg['activities'], MinSize=1, MaxSize=1, DesiredCapacity=1)
        time.sleep(1)

        print("Starting cachemanager")
        if not args.asg_only:
            ec2_client.start_instances(InstanceIds=[instance_ids[f"cachemanager.{args.bosslet_name}"]])
            time.sleep(1)          
    else:
        print("Stopping cachemanager")
        if not args.asg_only:
            ec2_client.stop_instances(InstanceIds=[instance_ids[f"cachemanager.{args.bosslet_name}"]])
            time.sleep(1)

        print("Scaling down activties")
        asg_client.update_auto_scaling_group(AutoScalingGroupName=bosslet_asg['activities'], MinSize=0, MaxSize=0, DesiredCapacity=0)
        time.sleep(1)

        print("Scaling down endpoint") 
        asg_client.update_auto_scaling_group(AutoScalingGroupName=bosslet_asg['endpoint'], MinSize=0, MaxSize=0, DesiredCapacity=0)
        time.sleep(1)

        print("Scaling down vault")
        asg_client.update_auto_scaling_group(AutoScalingGroupName=bosslet_asg['vault'], MinSize=0, MaxSize=0, DesiredCapacity=0)
        time.sleep(1)

        print("Stopping bastion")
        if not args.asg_only:
            ec2_client.stop_instances(InstanceIds=[instance_ids[f"bastion.{args.bosslet_name}"]])
            time.sleep(1)
        
    print('Done!')

def get_instance_id(ec2_client, instance_name):
    resp = ec2_client.describe_instances(Filters=[{"Name":"tag:Name", "Values": [instance_name]}])['Reservations']
    return resp[0]['Instances'][0]['InstanceId']

def wait_for_instance(ec2_client, instance_name):

    # Filters out the instances that were previously terminated but have the same name.
    filters = [
        {
            'Name': "tag:Name",
            'Values': [instance_name], 
        },
        {
            'Name': 'instance-state-name',
            'Values': ['pending', 'running', 'stopped']
        }
    ]

    waiter = ec2_client.get_waiter('instance_running')
    waiter.wait(
        Filters= filters,
        WaiterConfig={
            'Delay': 5
        }
    )

if __name__ == '__main__':
    parser = configuration.BossParser(description='Script to scale up or down all EC2 autoscale groups for a BossDB stack.')
    parser.add_bosslet()
    parser.add_argument('mode',
                        choices=('up', 'down'),
                        help="'up' to set capacities to 1, 'down' to set capacities to 0." )
    parser.add_argument('--asg-only', '-a',
                        action = 'store_true',
                        help = 'Only scale down ASG instances, keep cachemanager and bastion up.', 
                        default=False)
    args = parser.parse_args() 
    scale_stack(args)



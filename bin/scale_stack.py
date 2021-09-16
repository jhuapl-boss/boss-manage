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
"""

import boto3

import alter_path
from lib import configuration

PRODUCTION = ["bossdb.boss"]

def scale_stack(args):
    if args.bosslet_name in PRODUCTION:
        print("ERROR: Cannot scale down production environment.")
        return
    
    if args.mode not in ('up', 'down'): 
        print("ERROR: Incorrect mode. Can only be 'up' or 'down'.")
        return 
    
    session = args.bosslet_config.session
    
    ## Scale non-ASG instances, cachemanager and bastion, by stopping/starting them. ##
    if not args.asg_only:
        client = session.client('ec2')
        instances = (f"cachemanager.{args.bosslet_name}", f"bastion.{args.bosslet_name}")
        response = client.describe_instances(Filters=[{"Name":"tag:Name", "Values": instances}])['Reservations']
        instance_ids = [x['Instances'][0]['InstanceId'] for x in response]
        if args.mode == 'up':
            client.start_instances(InstanceIds=instance_ids)
        else:
            client.stop_instances(InstanceIds=instance_ids)

    ## Scale ASG instances by setting capacity to 0/1. ## 
    client = session.client('autoscaling')
    
    # Get ASG List
    response = client.describe_auto_scaling_groups()['AutoScalingGroups']
    
    # Filter those that belong to bosslet
    bosslet_id = args.bosslet_name.split('.')[0].lower()
    bosslet_asg = []
    for asg in response:
        if bosslet_id in asg['AutoScalingGroupName'].lower() and 'auth' not in asg['AutoScalingGroupName'].lower():
            bosslet_asg.append(asg)

    # Adjust desired, max, and min capacity for matched ASGs
    for asg in bosslet_asg:
        if args.mode == 'up':
            client.update_auto_scaling_group(AutoScalingGroupName=asg['AutoScalingGroupName'], MinSize=1, MaxSize=1, DesiredCapacity=1)
        else: 
            client.update_auto_scaling_group(AutoScalingGroupName=asg['AutoScalingGroupName'], MinSize=0, MaxSize=0, DesiredCapacity=0)

    


if __name__ == '__main__':
    parser = configuration.BossParser(description='Script to scale up or down all EC2 autoscale groups for a BossDB stack.')
    parser.add_bosslet()
    parser.add_argument('mode',
                        help="'up' to set capacities to 1, 'down' to set capacities to 0." )
    parser.add_argument('--asg-only', '-a',
                        action = 'store_true',
                        help = 'Only scale down ASG instances, keep cachemanager and bastion up.', 
                        default=True)
    args = parser.parse_args() 
    scale_stack(args)



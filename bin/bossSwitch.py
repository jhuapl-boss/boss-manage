#!/usr/bin/env python3.5

# Copyright 2016 The Johns Hopkins University Applied Physics Laboratory
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Script to turn the boss on and off.
   ASG are shut down. Only execute this code if you are certain the boss will not
   be running for another hour."""

import boto3
import sys
import json
import argparse
import os
import subprocess
import time

import alter_path
from lib import aws, utils, vault

def main():

    choice = utils.get_user_confirm("Are you sure you want to proceed switching the boss on/off?")
    if choice:
        if args.action == "on":
            print("Turning the BossDB on...")
            startInstances()

        elif args.action == "off":
            print("Turning the BossDB off...")
            stopInstances()

#Executed actions
def startInstances():

    #Start vault instance
    print("Starting vault...")
    client.update_auto_scaling_group(AutoScalingGroupName=vaultg, MinSize = 1 , MaxSize = 1 , DesiredCapacity = 1)
    client.resume_processes(AutoScalingGroupName=vaultg,ScalingProcesses=['HealthCheck'])
    time.sleep(120)
    print("Vault instance running")

    #Import vault content:
    subprocess.call('./bastion.py ' + args.vpc + ' vault-unseal',shell=True)
    print("Importing vault content")
    subprocess.call('./bastion.py ' + args.vpc + ' vault-import < ../config/vault_export.json', shell=True)
    print(bcolors.WARNING + "Successful import" + bcolors.ENDC)    

    #Start endpoint and activities instances
    print("Starting endpoint, and activities...")
    client.update_auto_scaling_group(AutoScalingGroupName=endpoint, MinSize = 1 , MaxSize = 1 , DesiredCapacity = 1)
    client.resume_processes(AutoScalingGroupName=endpoint,ScalingProcesses=['HealthCheck'])
    
    client.update_auto_scaling_group(AutoScalingGroupName=activities, MinSize = 1 , MaxSize = 1 , DesiredCapacity = 1)
    client.resume_processes(AutoScalingGroupName=activities,ScalingProcesses=['HealthCheck'])

    print(bcolors.OKGREEN + "TheBoss is on" + bcolors.ENDC)


def stopInstances():

    #Export vault content:
    print("Exporting vault content...")
    subprocess.call('./bastion.py ' + args.vpc + ' vault-export > ../config/vault_export.json', shell=True)
    print(bcolors.WARNING + "Successful export" + bcolors.ENDC)

    #Switch off:
    print("Stopping all Instances...")
    client.update_auto_scaling_group(AutoScalingGroupName=endpoint, MinSize = 0 , MaxSize = 0 , DesiredCapacity = 0)
    client.suspend_processes(AutoScalingGroupName=endpoint,ScalingProcesses=['HealthCheck'])

    client.update_auto_scaling_group(AutoScalingGroupName=activities, MinSize = 0 , MaxSize = 0 , DesiredCapacity = 0)
    client.suspend_processes(AutoScalingGroupName=activities,ScalingProcesses=['HealthCheck'])

    client.update_auto_scaling_group(AutoScalingGroupName=vaultg, MinSize = 0 , MaxSize = 0 , DesiredCapacity = 0)
    client.suspend_processes(AutoScalingGroupName=vaultg,ScalingProcesses=['HealthCheck'])

    print(bcolors.FAIL + "TheBoss is off" + bcolors.ENDC)


class bcolors:
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'


if __name__ == '__main__':

    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    actions = ["on", "off"]
    actions_help = create_help("action supports the following:", actions)

    scenarios = ["development", "production"]
    scenario_help = create_help("scenario supports the following:", scenarios)

    parser = argparse.ArgumentParser(description = "Script to turn the boss on and off by stopping and restarting EC2 instances.",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=actions_help + scenario_help)
    parser.add_argument("--aws-credentials", "-a",
                        metavar = "<file>",
                        default = "../config/aws-credentials",
                        help = "File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("--scenario",
                        metavar = "<scenario>",
                        default = "development",
                        choices = scenarios,
                        help = "The deployment configuration to use when creating the stack (instance size, autoscale group size, etc) (default: development)")
    parser.add_argument("action",
                        choices = actions,
                        metavar = "action",
                        help = "Action to execute")
    parser.add_argument("vpc",
                    metavar = "vpc-machine-name",
                    help = "The vault machine name. ex: vault.user.boss")
    args = parser.parse_args()

    #Loading AWS configuration files.
    creds = json.load(open(args.aws_credentials))
    aws_access_key_id = creds["aws_access_key"]
    aws_secret_access_key = creds["aws_secret_key"]
    region_name = 'us-east-1'

    if creds is None:
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")

    # specify AWS keys, sets up connection to the client.
    auth = {"aws_access_key_id": aws_access_key_id, "aws_secret_access_key": aws_secret_access_key, "region_name": region_name}
    client = boto3.client('autoscaling', **auth)

    if args.scenario == 'development':
        #Loading ASG configuration files. Please specify your ASG names on asg-cfg found in the config file.
        asg = json.load(open('../config/asg-cfg-dev'))
        activities = asg["activities"]
        endpoint = asg["endpoint"]
        auth = asg["auth"]
        vaultg = asg["vault"]
        consul = asg["consul"]

    elif args.scenario == 'production':
        #Loading ASG configuration files. Please specify your ASG names on asg-cfg found in the config file.
        asg = json.load(open('../config/asg-cfg'))
        activities = asg["activities"]
        endpoint = asg["endpoint"]
        auth = asg["auth"]
        vaultg = asg["vault"]
        consul = asg["consul"]

    else:
        raise NameError('The asg-cfg or asg-cfg-dev need to exist.')

    main()

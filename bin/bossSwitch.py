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
   The script aims at switch the boss on and off once it has been configured a first time.
   The instances should first be stood up by building stacks through cloudformation.
   ASG are shut down. Only execute this code if you are certain the boss will not
   be running for another hour."""

import boto3
import sys
import json
import argparse
import os
import subprocess
import time
import pickle
import vault as vaultB
from lib.ssh import SSHConnection, vault_tunnel
from lib import aws, utils, vault, constants, external

def main():

    choice = utils.get_user_confirm("Are you sure you want to proceed?")
    if choice:
        if args.action == "on":
            print("Turning the BossDB on...")
            startInstances()

        elif args.action == "off":
            print("Turning the BossDB off...")
            stopInstances()

#Executed actions
def startInstances():
    """
        Method used to start necessary instances
    """
    #Use auto scaling groups last saved configuration
    try:
        ASGdescription = load_obj('ASGdescriptions')
        activitiesD = [ASGdescription["AutoScalingGroups"][0]["MinSize"], ASGdescription["AutoScalingGroups"][0]["MaxSize"],ASGdescription["AutoScalingGroups"][0]["DesiredCapacity"]]
        endpointD = [ASGdescription["AutoScalingGroups"][1]["MinSize"], ASGdescription["AutoScalingGroups"][1]["MaxSize"],ASGdescription["AutoScalingGroups"][1]["DesiredCapacity"]]
        vaultD = [ASGdescription["AutoScalingGroups"][2]["MinSize"], ASGdescription["AutoScalingGroups"][2]["MaxSize"],ASGdescription["AutoScalingGroups"][2]["DesiredCapacity"]]
    except Exception as e:
       utils.console.fail("Unsuccessful ASG configuration")
       print("Error due to: %s" % e)
       exit()

    #Start vault instance
    print("Starting vault...")
    client.update_auto_scaling_group(AutoScalingGroupName=vaultg, MinSize = vaultD[0] , MaxSize =  vaultD[1], DesiredCapacity = vaultD[2])
    client.resume_processes(AutoScalingGroupName=vaultg,ScalingProcesses=['HealthCheck'])
    time.sleep(constants.TIMEOUT_VAULT)
    print("Vault instance running")

    #Import vault content:
    print("Importing vault content")
    try:
        with vault_tunnel(args.ssh_key, bastion):
            private = aws.machine_lookup(session,args.vpc,public_ip=False)
            vaultB.vault_unseal(vault.Vault(args.vpc, private))
            vaultB.vault_import(vault.Vault(args.vpc, private), real_path + '/config/vault_export.json')
        utils.console.okgreen("Successful import")
    except Exception as e:
        utils.console.fail("Unsuccessful import")
        print("Error due to %s" % e)
        exit()

    #Start endpoint and activities instances
    print("Starting endpoint, and activities...")
    try:
        client.update_auto_scaling_group(AutoScalingGroupName=endpoint, MinSize = endpointD[0] , MaxSize = endpointD[1] , DesiredCapacity = endpointD[2])
        client.resume_processes(AutoScalingGroupName=endpoint,ScalingProcesses=['HealthCheck'])
        
        client.update_auto_scaling_group(AutoScalingGroupName=activities, MinSize = activitiesD[0] , MaxSize = activitiesD[1] , DesiredCapacity = activitiesD[2])
        client.resume_processes(AutoScalingGroupName=activities,ScalingProcesses=['HealthCheck'])
    except Exception as e:
        print('Error: %s' % e)
        exit()

    utils.console.okgreen("TheBoss is on")


def stopInstances():
    """
        Method used to stop currently running instances
    """
    #Save current ASG descriptions:
    print("Saving current auto scaling group configuration...")
    response = client.describe_auto_scaling_groups(AutoScalingGroupNames=[endpoint,activities,vaultg])
    try:
        response['AutoScalingGroups'][0]
        save_obj(response,'ASGdescriptions')
        print("Successfully saved ASG descriptions")
    except IndexError as e:
        utils.console.fail("Failed while saving ASG descriptions")
        print("Error: %s" % e)
        exit()

    #Export vault content:
    print("Exporting vault content...") 
    try:
        with vault_tunnel(args.ssh_key, bastion): 
            vaultB.vault_export(vault.Vault(args.vpc, private), real_path+'/config/vault_export.json')
        utils.console.okgreen("Successful vaul export")
    except Exception as e:
        utils.console.fail("Unsuccessful vault export")
        print("Error: %s" % e)
        exit()

    #Switch off:
    print("Stopping all Instances...")
    client.update_auto_scaling_group(AutoScalingGroupName=endpoint, MinSize = 0 , MaxSize = 0 , DesiredCapacity = 0)
    client.suspend_processes(AutoScalingGroupName=endpoint,ScalingProcesses=['HealthCheck'])

    client.update_auto_scaling_group(AutoScalingGroupName=activities, MinSize = 0 , MaxSize = 0 , DesiredCapacity = 0)
    client.suspend_processes(AutoScalingGroupName=activities,ScalingProcesses=['HealthCheck'])

    client.update_auto_scaling_group(AutoScalingGroupName=vaultg, MinSize = 0 , MaxSize = 0 , DesiredCapacity = 0)
    client.suspend_processes(AutoScalingGroupName=vaultg,ScalingProcesses=['HealthCheck'])

    utils.console.fail("TheBoss is off")

def save_obj(obj, name ):
    """
        Method to save objects as .pkl files

        Args:
            obj : The object that will be saved
            name : The .pkl file name under which the object will be saved
    """
    with open(real_path + '/' + name + '.pkl', 'wb') as f:
        pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)

def load_obj(name):
    """
        Method to load saved objects in .pkl file

        Args:
            name : The .pkl file name to open
        
        Returns:
            object saved within .pkl file
    """
    with open(real_path + '/' + name + '.pkl', 'rb') as f:
        return pickle.load(f)

if __name__ == '__main__':

    #Grab files path to use as reference.
    real_path = constants.repo_path()

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
                        default = "aws-credentials",
                        help = "File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("--scenario",
                        metavar = "<scenario>",
                        default = "development",
                        choices = scenarios,
                        help = "The deployment configuration to use when creating the stack (instance size, autoscale group size, etc) (default: development)")
    parser.add_argument("--config",
                        metavar = "<config>",
                        default ="asg-cfg-dev",
                        help = "Name of auto scale group configuration file located inside boss-manage/config folder")
    parser.add_argument("--private-ip", "-p",
                        action='store_true',
                        default=False,
                        help = "add this flag to type in a private IP address in internal command instead of a DNS name which is looked up")
    parser.add_argument("--user", "-u",
                        default='ubuntu',
                        help = "Username of the internal machine")
    parser.add_argument("--port",
                        default=22,
                        type=int,
                        help = "Port to connect to on the internal machine")
    parser.add_argument("--ssh-key", "-s",
                        metavar = "<file>",
                        default = os.environ.get("SSH_KEY"),
                        help = "SSH private key to use when connecting to AWS instances (default: SSH_KEY)")
    parser.add_argument("--bastion","-b",  help="Hostname of the EC2 bastion server to create SSH Tunnels on")
    parser.add_argument("action",
                        choices = actions,
                        metavar = "action",
                        help = "Action to execute")
    parser.add_argument("vpc",
                    metavar = "vpc-machine-name",
                    help = "The vault machine name. ex: vault.user.boss")
    args = parser.parse_args()

    #Loading AWS configuration files.
    creds = json.load(open(str(real_path + '/config/' + args.aws_credentials)))
    aws_access_key_id = creds["aws_access_key"]
    aws_secret_access_key = creds["aws_secret_key"]
    region_name = constants.REGION

    if creds is None:
        raise Exception('AWS credentials not provided')

    # specify AWS keys, sets up connection to the client.
    session = aws.create_session(creds)
    client = session.client('autoscaling')

    # This next code block was adopted from bin/bastion.py and sets up vault_tunnel
    boss_position = 1
    try:
        int(args.vpc.split(".", 1)[0])
        boss_position = 2
    except ValueError:
        pass
    bastion_host = args.bastion if args.bastion else "bastion." + args.vpc.split(".", boss_position)[boss_position]
    bastion = aws.machine_lookup(session, bastion_host)
    if args.private_ip:
        private = args.vpc
    else:
        private = aws.machine_lookup(session, args.vpc, public_ip=False)

    ssh = SSHConnection(args.ssh_key, (private, args.port, args.user), bastion)

    #Loading ASG configuration files. Please specify your ASG names on asg-cfg found in the config file.
    asg = json.load(open(str(real_path + '/config/' + args.config)))
    activities = asg["activities"]
    endpoint = asg["endpoint"]
    vaultg = asg["vault"]
    auth = asg["auth"]

    main()

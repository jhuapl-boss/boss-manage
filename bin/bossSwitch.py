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
   The script aims to switch the boss on and off once it has been configured a first time.
   The instances should first be stood up by building stacks through cloudformation.
   ASG are shut down. Only execute this code if you are certain the boss will not
   be running for another hour.
   Currently not all of the ASGs are supported. The auth and consul ASGs could present problems
   if shut down, since all their data would be lost and would not be recovered upon turning the boss on. 
   Supporting Auth ASG could be done using the same check the core config uses to see ig an auth RDS should be create.
   If there is an auth db then you should be able to shut the ec2 instances down."""

import boto3
import sys
import json
import argparse
import os
import subprocess
import time
import pickle

import alter_path
import vault as vaultB
from lib.ssh import SSHTarget, vault_tunnel
from lib import aws, utils, vault, constants
from lib.configuration import BossParser

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
        print("Successful ASG configuration")
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
        with vault_tunnel(bosslet_config.ssh_key, bastions):
            vaultB.vault_unseal(vault_client)
            vaultB.vault_import(vault_client, REAL_PATH + '/config/vault_export.json')
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
        with vault_tunnel(bosslet_config.ssh_key, bastions): 
            vaultB.vault_export(vault_client, REAL_PATH+'/config/vault_export.json')
        utils.console.warning("Please protect the vault_pexport.json file as it contains personal passwords.")
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
    with open(REAL_PATH + '/' + name + '.pkl', 'wb') as f:
        pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)

def load_obj(name):
    """
        Method to load saved objects in .pkl file

        Args:
            name : The .pkl file name to open
        
        Returns:
            object saved within .pkl file
    """
    with open(REAL_PATH + '/' + name + '.pkl', 'rb') as f:
        return pickle.load(f)

if __name__ == '__main__':

    #Grab files path to use as reference.
    REAL_PATH = constants.repo_path()

    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    actions = ["on", "off"]
    actions_help = create_help("action supports the following:", actions)

    parser = BossParser(description = "Script to turn the boss on and off by stopping and restarting EC2 instances.",
                        formatter_class=argparse.RawDescriptionHelpFormatter,
                        epilog=actions_help)
    parser.add_argument("--config",
                        metavar = "<config>",
                        default ="asg-cfg-dev",
                        help = "Name of auto scale group configuration file located inside boss-manage/config folder")
    parser.add_argument("action",
                        choices = actions,
                        metavar = "action",
                        help = "Action to execute")
    parser.add_bosslet()
    args = parser.parse_args()

    bosslet_config = args.bosslet_config

    # Lookup bosslet bastion information and add any outbound bastion
    bastion = aws.machine_lookup(bosslet_config.session,
                                 bosslet_config.names.dns.bastion) 
    bastions = [SSHTarget(bosslet_config.ssh_key, bastion, 22, 'ec2-user')]
    if bosslet_config.outbound_bastion:
        bastions.insert(0, bosslet_config.outbound_bastion)

    # Lookup vault information and create client
    vault_ip = aws.machine_lookup(bosslet_config.session,
                                  bosslet_config.names.dns.vault) 
    vault_client = vault.Vault(bosslet_config.names.dns.vault, vault_ip)

    # Create Boto3 session
    client = bosslet_config.session.client('autoscaling')

    #Loading ASG configuration files. Please specify your ASG names on asg-cfg found in the config file.
    asg = json.load(open(str(REAL_PATH + '/config/' + args.config)))
    activities = asg["activities"]
    endpoint = asg["endpoint"]
    vaultg = asg["vault"]
    auth = asg["auth"]

    main()

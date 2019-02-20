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
from lib import utils, constants, console
from lib.configuration import BossParser

# Cannot stop consul without losing data
# Could do it if Vault was first re-initialized and configured
# and then existing data imported

"""
Error conditions and handling

Code should be able to handle multiple calls to on or off in a row
and only work with the machines that didn't get turned on or off

ex: On -> Vault failure, Manually fix Vault, On to finish all other instances

Should prompt for turning Consul off?
What about when no ASGs exist for the bosslet?

Starting:
    An error when starting ASG that is off - 
    Starting ASG that already is on - 
    Initializing Vault - 
    Unsealing Vault - 
    Exported Vault data not existing - 
    Importing Vault data - 


Stopping:
    An error when stopping ASG that is on - 
    Stopping ASG that is already off - 
    Exporting Vault data - 
    Stopping Auth without RDS - 
"""

VAULT_FILE = constants.repo_path('vault', 'private', '{}', 'export.json')

def load_aws(bosslet_config, method):
    suffix = '.' + bosslet_config.INTERNAL_DOMAIN

    client = bosslet_config.session.client('autoscaling')
    response = client.describe_auto_scaling_groups()

    def name(tags):
        for tag in tags:
            if tag['Key'] == 'Name':
                return tag['Value']
        return ""

    asgs = [AutoScalingGroup(bosslet_config, asg)
            for asg in response['AutoScalingGroups']
            if name(asg['Tags']).endswith(suffix) ]

    if method == 'on':
        for asg in asgs:
            asg.load_tags()
    elif method == 'off':
        for asg in asgs:
            asg.save_tags()

    return load_sort(asgs, method)

def load_sort(asgs, method):
    unsorted = asgs.copy()
    sorted = []

    def pop(name):
        for i in range(len(unsorted)):
            if name in unsorted[i].name:
                return unsorted.pop(i)

    def add(name):
        obj = pop(name)
        if obj:
            sorted.append(obj)

    add('Consul')
    add('Vault')
    sorted.extend(unsorted)

    if method == "off":
        sorted.reverse()

    return sorted

class AutoScalingGroup(object):
    def __init__(self, bosslet_config, definition):
        self.bosslet_config = bosslet_config
        self.client = bosslet_config.session.client('autoscaling')
        self.definition = definition

        self.name = definition['AutoScalingGroupName']

        self.min = definition['MinSize']
        self.max = definition['MaxSize']
        self.desired = definition['DesiredCapacity']

    def start(self):
        if DRY_RUN:
            print("Setting {} to {}/{}/{}".format(self.name,
                                                  self.min,
                                                  self.max,
                                                  self.desired))
        else:
            self.client.update_auto_scaling_group(AutoScalingGroupName = self.name,
                                                  MinSize = self.min,
                                                  MaxSize = self.max,
                                                  DesiredCapacity = self.desired)

            self.client.resume_processes(AutoScalingGroupName = self.name,
                                         ScalingProcesses = ['HealthCheck'])

    def stop(self):
        if DRY_RUN:
            print("Setting {} to 0/0/0".format(self.name))
        else:
            self.client.update_auto_scaling_group(AutoScalingGroupName = self.name,
                                                  MinSize = 0,
                                                  MaxSize = 0,
                                                  DesiredCapacity = 0)

            self.client.suspend_processes(AutoScalingGroupName = self.name,
                                          ScalingProcesses = ['HealthCheck'])

    def save_tags(self):
        pass # TODO Luis
        # Create tags to store current self.min / self.max / self.desired
        # use self.client to interact with AWS

        # Non-standard situations to think about
        # Saving tags when tags already exist and have different values
        # Loading tags when self.min / self.max / self.desired are not 0/0/0
        # Saving tags when self.min / self.max / self.desired are already 0/0/0
    def load_tags(self):
        pass # TODO Luis
        # set self.min / self.max / self.desired based on tags in self.definition
        # Should there be a call to AWS to remove the tags?

#Executed actions
def startInstances(bosslet_config):
    """
        Method used to start necessary instances
    """

    # Verify Vault data exists before continuing
    filename = VAULT_FILE.format(bosslet_config.names.vault.dns)
    if not os.path.exists(filename):
        msg = "File {} doesn't exist, cannot reimport Vault data".format(filename)
        if DRY_RUN:
            console.warning(msg)
        else:
            console.fail(msg)
            return

    asg_problem = False
    consul_started = False

    asgs = load_aws(bosslet_config, 'on')
    for asg in asgs:
        print(asg.name)
    for asg in asgs:
        # TODO: Add error handling
        # If Vault error, stop
        # If error starting ASG log error and continue

        ###############################
        # Pre-start actions or checks #
        ###############################

        if 'Auth' in asg.name:
            if not bosslet_config.AUTH_RDS:
                console.warning("Skipping starting Auth ASG, as it was not stopped")
                continue

        ###################
        # Start Instances #
        ###################

        print("Turning on {}".format(asg.name))
        try:
            asg.start()
            console.green("{} is on".format(asg.name))
        except Exception as ex:
            asg_problem = True
            console.warning("{} is not on".format(asg.name))
            print(ex)

        ################################
        # Post-start actions or checks #
        ################################

        if 'Consul' in asg.name:
            consul_started = True
        if 'Vault' in asg.name:
            if DRY_RUN:
                print("Waiting for Vault to start")
                if not consul_started:
                    print("Vault unseal")
                else:
                    print("Vault initialize")
                    print("Vault unseal")
                    print("Vault configure")
                print("Vault import {}".format(filename))
                continue

            print("Waiting for Vault to start")
            # XXX: May need to wait a little before creating call, so that
            #      vault instances are named and can be resolved
            bosslet_config.call.check_vault(constants.TIMEOUT_VAULT)

            with bosslet_config.call.vault() as vault:
                if not consul_started:
                    vault.unseal()
                else:
                    print("Initializing Vault...")
                    try:
                        vault.initialize(bosslet_config.ACCOUNT_ID)
                    except Exception as ex:
                        filename = VAULT_FILE.format(bosslet_config.names.vault.dns)
                        print(ex)
                        print("Could not initialize Vault")
                        print("Call the following commands before trying to turn the bosslet back on")
                        print(" > bin/bastion.py vault.<bosslet> vault-initialize")
                        print(" > bin/bastion.py vault.<bosslet> vault-import {}".format(filename))
                        return

                print("Importing previous Vault data")
                try:
                    with open(filename) as fh:
                        data = json.load(fh)
                    vault.import_(data)
                    console.green("Successful import")
                except Exception as e:
                    console.fail("Unsuccessful import")
                    print(ex)
                    print("Cannot continue restore")
                    return

    if asg_problem:
        console.warning("Problems turning on bosslet")
    else:
        console.blue("Bosslet is on")


def stopInstances(bosslet_config):
    """
        Method used to stop currently running instances
    """
    filename = VAULT_FILE.format(bosslet_config.names.vault.dns)

    asg_problem = False

    asgs = load_aws(bosslet_config, 'off')
    for asg in asgs:
        print(asg.name)
    for asg in asgs:
        ##############################
        # Pre-stop actions or checks #
        ##############################

        if 'Vault' in asg.name:
            if DRY_RUN:
                print("Export Vault data into {}".format(filename))
            else:
                print("Exporting current Vault data")
                try:
                    with bosslet_config.call.vault() as vault:
                        # TODO: figure out what configuration information should be exported
                        data = vault.export("secret/")

                        with open(filename, 'w') as fh:
                            json.dump(data, fh, indent=3, sort_keys=True)

                    console.warning("Please protect {} as it contains personal passwords".format(filename))
                    console.green("Successful Vault export")
                except Exception as e:
                    console.fail("Unsuccessful vault export")
                    print(ex)
                    print("Cannot continue")
                    return
        elif 'Auth' in asg.name:
            if not bosslet_config.AUTH_RDS:
                console.warning("Cannot turn off Auth ASG without an external RDS database")
                continue

        ##################
        # Stop Instances #
        ##################

        print("Turning off {}".format(asg.name))
        try:
            asg.stop()
            console.green("{} is off".format(asg.name))
        except Exception as ex:
            asg_problem = True
            console.warning("{} is not off".format(asg.name))
            print(ex)
            # XXX: What to do?

        ###############################
        # Post-stop actions or checks #
        ###############################
        # None right now

    if asg_problem:
        # XXX: The problem is that if 'off' is re-run the ASGs that were previously
        #      turned off will have 0/0/0 saved to the DEFINITION_FILE and mess up
        #      turning ASGs back on
        console.warning("Problem turning off bosslet")
    else:
        console.blue("TheBoss is off")

if __name__ == '__main__':
    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    actions = ["on", "off"]
    actions_help = create_help("action supports the following:", actions)

    parser = BossParser(description = "Script to turn the boss on and off by stopping and restarting EC2 instances.",
                        formatter_class=argparse.RawDescriptionHelpFormatter,
                        epilog=actions_help)
    parser.add_argument("--dry-run", "-n",
                        action = "store_true",
                        help = "If the actions should be dry runned")
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

    DRY_RUN = args.dry_run
    bosslet_config = args.bosslet_config

    choice = console.confirm("Are you sure you want to proceed?", timeout=30)
    if not choice:
        sys.exit(0)

    console.init()

    print("Turning the {} bosslet {}...".format(args.bosslet_name,
                                                args.action))

    try:
        if args.action == "on":
            startInstances(bosslet_config)
        elif args.action == "off":
            stopInstances(bosslet_config)
    except Exception as ex:
        print("Error due to %s" % e)
        sys.exit(1)

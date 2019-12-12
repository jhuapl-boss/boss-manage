#!/usr/bin/env python3.5

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

"""A script to test HA capabilities of the architecture

Author:
    Derek Pryor <Derek.Pryor@jhuapl.edu>
"""

import argparse
import sys
import random
from boto3.session import Session
import json
import os
import random
import time

import alter_path
from lib.configuration import BossParser

TARGET_MACHINES = [
    "vault",
    "auth",
]


def machine_lookup(bosslet_config, az):
    hostnames = [bosslet_config.names.dns[m] for m in TARGET_MACHINES]

    client = bosslet_config.session.client('ec2')
    response = client.describe_instances(Filters=[{"Name":"availability-zone", "Values":[az]},
                                                  {"Name":"tag:Name", "Values":hostnames},
                                                  {"Name":"instance-state-name", "Values":["running"]}])

    ids = []

    items = response['Reservations']
    if len(items) > 0:
        for i in items:
            item = i['Instances'][0]
            ids.append(item['InstanceId'])
    return ids

def azs_lookup(session):
    """Lookup all of the Availablity Zones for the connected region.

    Args:
        session (Session|None) : Boto3 session used to lookup information in AWS
                                 If session is None no lookup is performed

    Returns:
        (list) : List of availability zone names
    """
    client = session.client('ec2')
    response = client.describe_availability_zones()
    rtn = [z["ZoneName"] for z in response["AvailabilityZones"]]

    return rtn

def machine_terminate(session, instances):
    ec2 = session.resource('ec2')

    for instance in instances:
        ec2.Instance(instance).terminate()

def kill_az(bosslet_config, dryrun):
    azs = azs_lookup(bosslet_config.session)
    az = random.choice(azs)
    print("Selecting Availability Zone ", az)
    ids = machine_lookup(bosslet_config, az)
    if dryrun:
        for id in ids:
            print("Would terminate instance ", id)
    else:
        machine_terminate(bosslet_config.session, ids)


if __name__ == "__main__":
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    tests = {
        'kill-az': kill_az,
    }

    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    parser = BossParser(description = "Script to test killing all of the target EC2 instances in an availability zone",
                        formatter_class=argparse.RawDescriptionHelpFormatter,
                        epilog=create_help("test supports the following:", tests.keys()))

    parser.add_argument("--dryrun",
                        action = "store_true",
                        help = "Dry run and print the instances that would be terminated")
    parser.add_bosslet()
    parser.add_argument("test",
                        choices = tests.keys(),
                        metavar = "test",
                        help = "Which type of test to run")

    args = parser.parse_args()

    # TODO: add sub command to log into each target machine and shutdown the service (leave the machine running)

    ret = tests[args.test](args.bosslet_config, args.dryrun)
    if type(ret) == int:
        sys.exit(ret)
    elif type(ret) == bool:
        sys.exit(0 if ret else 1)


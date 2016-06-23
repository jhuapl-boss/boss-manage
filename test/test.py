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

Environmental Variables:
    AWS_CREDENTIALS : File path to a JSON encode file containing the following keys
                      "aws_access_key" and "aws_secret_key"

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

TARGET_MACHINES = [
    "consul.",
    "vault.",
    "auth."
]

def create_session(cred_fh):
    """Read AWS credentials from the given file object and create a Boto3 session.

        Note: Currently is hardcoded to connect to Region US-East-1

    Args:
        cred_fh (file) : File object of a JSON formated data with the following keys
                         "aws_access_key" and "aws_secret_key"

    Returns:
        (Session) : Boto3 session
    """
    credentials = json.load(cred_fh)

    session = Session(aws_access_key_id = credentials["aws_access_key"],
                      aws_secret_access_key = credentials["aws_secret_key"],
                      region_name = 'us-east-1')
    return session

def machine_lookup(session, domain, az):
    hostnames = [m + domain for m in TARGET_MACHINES]

    client = session.client('ec2')
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

if __name__ == "__main__":
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    parser = argparse.ArgumentParser(description = "Script to test killing all of the target EC2 instances in an availability zone")


    parser.add_argument("--aws-credentials", "-a",
                        metavar = "<file>",
                        default = os.environ.get("AWS_CREDENTIALS"),
                        type = argparse.FileType('r'),
                        help = "File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("--dryrun",
                        action = "store_true",
                        help = "Dry run and print the instances that would be terminated")
    parser.add_argument("domain",
                        metavar = "domain",
                        help = "Domain to target")

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    session = create_session(args.aws_credentials)

    # TODO: add sub command argument and move current functionality into a function
    # TODO: add sub command to log into each target machine and shutdown the service (leave the machine running)
    azs = azs_lookup(session)
    az = random.choice(azs)
    print("Selecting Availability Zone ", az)
    ids = machine_lookup(session, args.domain, az)
    if args.dryrun:
        for id in ids:
            print("Would terminate instance ", id)
    else:
        machine_terminate(session, ids)

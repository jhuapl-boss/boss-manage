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
import time

import alter_path
from lib import aws
from lib.external import ExternalCalls

TARGET_MACHINES = [
    "consul.",
    "vault.",
    "auth."
]


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

def kill_az(session, args):
    azs = azs_lookup(session)
    az = random.choice(azs)
    print("Selecting Availability Zone ", az)
    ids = machine_lookup(session, args.domain, az)
    if args.dryrun:
        for id in ids:
            print("Would terminate instance ", id)
    else:
        machine_terminate(session, ids)

ITERATIONS = 5 # DP TODO: make optional argument
def test_consul(session, args):
    if args.ssh_key is None:
        print("Error: SSH key not provided and SSH_KEY is not defined")
        return 1
    if not os.path.exists(args.ssh_key):
        print("Error: SSH key '{}' does not exist".format(args.ssh_key))
        return 1

    global TARGET_MACHINES
    TARGET_MACHINES = ['consul.'] # Limit to only consul
    calls = ExternalCalls(session, args.ssh_key, args.domain)

    azs = azs_lookup(session)
    for i in range(ITERATIONS):
        az = random.choice(azs)
        print("Selecting Availability Zone ", az)

        ids = machine_lookup(session, args.domain, az)
        for id in ids:
            print("Terminating instance ", id)
        machine_terminate(session, ids)

        print("Sleeping for 5 minutes")
        time.sleep(5 * 60)

        try:
            with calls.vault() as vault:
                result = vault.read("secret/auth/realm")
                username = result['data']['username']
                print("Read username '{}' from Vault".format(username))
        except Exception as e:
            print("Problem connecting to Vault on iteration ", i)
            print(e)
            return 1

        print()

    print("Complete")
    return 0

if __name__ == "__main__":
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    tests = {
        'kill-az': kill_az,
        'test-consul': test_consul,
    }

    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    parser = argparse.ArgumentParser(description = "Script to test killing all of the target EC2 instances in an availability zone",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=create_help("test supports the following:", tests.keys()))

    parser.add_argument("--aws-credentials", "-a",
                        metavar = "<file>",
                        default = os.environ.get("AWS_CREDENTIALS"),
                        type = argparse.FileType('r'),
                        help = "File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("--ssh-key", "-s",
                        metavar = "<file>",
                        default = os.environ.get("SSH_KEY"),
                        help = "SSH private key to use when connecting to AWS instances (default: SSH_KEY)")
    parser.add_argument("--dryrun",
                        action = "store_true",
                        help = "Dry run and print the instances that would be terminated")
    parser.add_argument("domain",
                        metavar = "domain",
                        help = "Domain to target")
    parser.add_argument("test",
                        choices = tests.keys(),
                        metavar = "test",
                        help = "Which type of test to run")

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    session = aws.create_session(args.aws_credentials)
    # TODO: add sub command to log into each target machine and shutdown the service (leave the machine running)

    ret = tests[args.test](session, args)
    if type(ret) == int:
        sys.exit(ret)
    elif type(ret) == bool:
        sys.exit(0 if ret else 1)


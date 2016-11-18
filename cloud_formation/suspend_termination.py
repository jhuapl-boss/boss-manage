#!/usr/bin/env python3

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

"""
Command to suspend the termination and healthchecks processes of an autoscaling group
based off of http://docs.aws.amazon.com/autoscaling/latest/userguide/as-suspend-resume-processes.html
"""

import argparse
import sys
import os
import boto3
import json
from boto3 import Session
from botocore.exceptions import ClientError
import hosts
import pprint
import library as lib
import datetime

IAM_CONFIG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "iam"))
ENDPOINT = "endpoint"
VAULT = "vault"
AUTH = "auth"
CONSUL = "consul"
ASGS = [ENDPOINT, VAULT, AUTH, CONSUL]

def create_help(header, options):
    """Create formated help."""
    return "\n" + header + "\n" + \
           "\n".join(map(lambda x: "  " + x, options)) + "\n"

asg_help = create_help("asg defaults to endpoint, options are", ASGS)

def get_asg_subname(domain, asg_name):
    """

    Args:
        domain: domain like hiderrt1.boss
        asg_name: One of the asg names in ASGS

    Returns:
        subname of Actual asg.  Used to search for the full asg name.
    """
    components = domain.split(".")
    title_domain = "".join(x.title() for x in components)
    if asg_name == ENDPOINT:
        return "Api" + title_domain + "-" + ENDPOINT.title()
    else:
        return "Core" + title_domain + "-" + asg_name.title()


def get_asg_full_name(session, domain, asg_name):
    """
    gets the full name of the asg.
    Args:
        session:
        domain: domain name (ex: hiderrt1.boss)
        asg_name: asg name listed in ASGS

    Returns:

    """
    asg_sub_name = get_asg_subname(domain, asg_name)
    client = session.client("autoscaling")
    paginator = client.get_paginator('describe_auto_scaling_groups')
    response_iterator = paginator.paginate(
        #AutoScalingGroupNames=[],
        #PaginationConfig={'MaxItems': 100, 'PageSize': 100000}
       )
    for resp in response_iterator:
        for asg in resp["AutoScalingGroups"]:
            if asg["AutoScalingGroupName"].startswith(asg_sub_name):
                return asg["AutoScalingGroupName"]
    return None


def suspend_termination(session, domain, asg_name, reverse=False):
    """
    Suspends the ASG Processes Termination and HealthCheck or puts them back online
    Args:
        session:
        domain: domain name (ex: hiderrt1.boss)
        asg_name: asg name listed in ASGS
        reverse: If True Resumes the processes

    Returns:
    """
    client = session.client("autoscaling")
    asg_name_full_name = get_asg_full_name(session, domain, asg_name)
    if asg_name_full_name is None:
        print("Cannot find a asg for {} in {}".format(asg_name, domain))
        return
    if reverse:
        response = client.resume_processes(AutoScalingGroupName=asg_name_full_name,
                                           ScalingProcesses=["Terminate","HealthCheck"])
    else:
        response = client.suspend_processes(AutoScalingGroupName=asg_name_full_name,
                                            ScalingProcesses=["Terminate","HealthCheck"])

    if response["ResponseMetadata"]["HTTPStatusCode"] != 200:
        print("Failed with HTTPStatusCode: " + response["HTTPStatusCode"])
        return
    if reverse:
        print("ONLINE: Termination and HealthCheck processes are back online for asg: " + asg_name_full_name)
    else:
        print("SUSPENDED: Termination and HealthCheck processes are suspended for asg: " + asg_name_full_name)


def create_session(credentials):
    """
    Read the AWS from the credentials dictionary and then create a boto3
    connection to AWS with those credentials.
    Args:
        credentials: AWS credentials in JSON format

    Returns: results boto3 AWS session object

    """
    session = Session(aws_access_key_id=credentials["aws_access_key"],
                      aws_secret_access_key=credentials["aws_secret_key"],
                      region_name='us-east-1')
    return session


if __name__ == '__main__':
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    parser = argparse.ArgumentParser(description="Suspend ASG healthchecks and termination processes or enable them again",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                      epilog=asg_help)
    parser.add_argument("--aws-credentials", "-a",
                        metavar="<file>",
                        default=os.environ.get("AWS_CREDENTIALS"),
                        type=argparse.FileType('r'),
                        help="File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("--reverse", "-r",
                        action="store_true",
                        default=False,
                        help="This flag reverses the suspension and puts Termination and HeatlhChecks back online")
    parser.add_argument("--asg",
                        metavar="<asg>",
                        default=ENDPOINT,
                        choices=ASGS,
                        help="The deployment configuration to use when creating the stack (instance size, autoscale group size, etc) (default: development)")
    parser.add_argument("domain_name",
                        help="Domain in which to execute the configuration (example: hiderrt1.boss)")

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    credentials = json.load(args.aws_credentials)
    session = create_session(credentials)
    suspend_termination(session, args.domain_name, args.asg, args.reverse)




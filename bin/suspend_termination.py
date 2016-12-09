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

import alter_path
from lib import aws

def suspend_termination(session, hostname, reverse=False):
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
    asg_name_full_name = aws.asg_name_lookup(session, hostname)
    if asg_name_full_name is None:
        print("Cannot find a asg for {}".format(hostname))
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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Suspend ASG healthchecks and termination processes or enable them again",
                                     formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("--aws-credentials", "-a",
                        metavar="<file>",
                        default=os.environ.get("AWS_CREDENTIALS"),
                        type=argparse.FileType('r'),
                        help="File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("--reverse", "-r",
                        action="store_true",
                        default=False,
                        help="This flag reverses the suspension and puts Termination and HeatlhChecks back online")
    parser.add_argument("hostname",
                        help="Hostname of EC2 instances that the target ASG maintains (example: endpoint.integration.boss)")

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    session = aws.create_session(args.aws_credentials)
    suspend_termination(session, args.hostname, args.reverse)




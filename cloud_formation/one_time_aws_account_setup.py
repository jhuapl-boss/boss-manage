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
"""Script to perform one time initialization on a new AWS Account to be use for TheBoss"""

import argparse
import sys
import os
from boto3.session import Session
import json
import library as lib
import configs.cloudwatch as cloudwatch
import iam_utils

PRODUCTION_MAILING_TOPIC = cloudwatch.PRODUCTION_MAILING_LIST
PRODUCTION_BILLING_TOPIC = "ProductionBillingList"
MAX_ALARM_DOLLAR = 30  # Maximum size of alarms in $1,000s

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

def create_billing_alarms(session):
    print("creating billing alarms")
    billing_topic_arn = lib.sns_topic_lookup(session, PRODUCTION_BILLING_TOPIC)
    client = session.client("cloudwatch")
    alarm_parms = {
        'AlarmName': 'Billing_1k',
        'AlarmDescription': 'Alarm when spending reaches 1k',
        'ActionsEnabled': True,
        'OKActions': [],
        'AlarmActions': [billing_topic_arn],
        'InsufficientDataActions': [],
        'MetricName': 'EstimatedCharges',
        'Namespace': 'AWS/Billing',
        'Statistic': 'Maximum',
        'Dimensions': [{'Name': 'Currency', 'Value': 'USD'}],
        'Period': 21600,
        'EvaluationPeriods': 1,
        'Threshold': 1000.0,
        'ComparisonOperator': 'GreaterThanOrEqualToThreshold'
    }

    for num in range(1, MAX_ALARM_DOLLAR + 1):
        print("   {}k".format(str(num)))
        alarm_parms['AlarmName'] = "Billing_{}k".format(str(num))
        alarm_parms['AlarmDescription'] = "Alarm when spending reaches {}k".format(str(num))
        alarm_parms['Threshold'] = float(num * 1000)
        response = client.put_metric_alarm(**alarm_parms)

def create_initial_sns_accounts(session):
    print("Creating SNS Topics.")
    topic_arn = lib.sns_create_topic(session, PRODUCTION_MAILING_TOPIC)
    if topic_arn == None:
        print("Failed to create {} topic".format(PRODUCTION_MAILING_TOPIC))

    topic_arn = lib.sns_create_topic(session, PRODUCTION_BILLING_TOPIC)
    if topic_arn == None:
        print("Failed to create {} topic".format(PRODUCTION_BILLING_TOPIC))

def import_iam_details_from_files(session):
    iam = iam_utils.IamUtils(session)
    iam.get_iam_details_from_aws()
    iam.load_from_files()
    print("Importing iam details to aws..")
    iam.import_to_aws()


if __name__ == '__main__':
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    parser = argparse.ArgumentParser(description="This script does some initial configuration of a new AWS Account to function as theboss.  It should only be run once on an AWS Account.",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog='one time setup for new AWS Account')
    parser.add_argument("--aws-credentials", "-a",
                        metavar="<file>",
                        default=os.environ.get("AWS_CREDENTIALS"),
                        type=argparse.FileType('r'),
                        help="File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("init", help="command to initialize the account with TheBoss settings")

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    credentials = json.load(args.aws_credentials)
    session = create_session(credentials)

    create_initial_sns_accounts(session)
    create_billing_alarms(session)
    import_iam_details_from_files(session)
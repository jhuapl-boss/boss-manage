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
import iam_utils

import alter_path
from lib import aws
from lib import constants as const
from lib import configuration

def create_billing_alarms(session):
    print("creating billing alarms")
    billing_topic_arn = aws.sns_topic_lookup(session, const.PRODUCTION_BILLING_TOPIC)
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
        'Period': 10,
        'EvaluationPeriods': 1,
        'Threshold': 1000.0,
        'ComparisonOperator': 'GreaterThanOrEqualToThreshold'
    }

    for num in range(1, const.MAX_ALARM_DOLLAR + 1):
        print("   {}k".format(str(num)))
        alarm_parms['AlarmName'] = "Billing_{}k".format(str(num))
        alarm_parms['AlarmDescription'] = "Alarm when spending reaches {}k".format(str(num))
        alarm_parms['Threshold'] = float(num * 1000)
        response = client.put_metric_alarm(**alarm_parms)

def create_initial_sns_accounts(session):
    print("Creating SNS Topics.")
    topic_arn = aws.sns_create_topic(session, const.PRODUCTION_MAILING_LIST)
    if topic_arn == None:
        print("Failed to create {} topic".format(const.PRODUCTION_MAILING_LIST))

    topic_arn = aws.sns_create_topic(session, const.PRODUCTION_BILLING_TOPIC)
    if topic_arn == None:
        print("Failed to create {} topic".format(const.PRODUCTION_BILLING_TOPIC))


def import_iam_details_from_files(bosslet_config):
    iam = iam_utils.IamUtils(bosslet_config)
    iam.get_iam_details_from_aws()
    iam.load_from_files()
    print("Importing iam details to aws..")
    iam.import_to_aws()


if __name__ == '__main__':
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    parser = configuration.BossParser(description="This script does some initial configuration of a new AWS Account " +
                                                  "to function as theboss.  It should only be run once on an AWS Account.",
                                      formatter_class=argparse.RawDescriptionHelpFormatter,
                                      epilog='one time setup for new AWS Account')
    parser.add_bosslet()

    args = parser.parse_args()

    create_initial_sns_accounts(args.bosslet_config.session)
    create_billing_alarms(args.bosslet_config.session)
    import_iam_details_from_files(args.bosslet_config)

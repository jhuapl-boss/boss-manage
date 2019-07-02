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

import alter_path
from lib import aws
from lib import configuration
from lib import console

try:
    import simpleeval
    eval = simpleeval.EvalWithCompoundTypes(functions={'range': range}).eval
except ImportError:
    console.warning("Library 'simpleeval' not available, using the default python implementation")

class SubscriptionList(object):
    def __init__(self, bosslet_config, topic):
        self.bosslet_config = bosslet_config
        self.client = bosslet_config.session.client('sns')
        self.topic = topic
        self.arn = self.to_arn(topic)

    def to_arn(self, topic):
        return 'arn:aws:sns:{}:{}:{}'.format(self.bosslet_config.REGION,
                                             self.bosslet_config.ACCOUNT_ID,
                                             topic)

    def create(self):
        console.info("Creating {} SNS topic".format(self.topic))
        session = self.bosslet_config.session
        arn = aws.sns_create_topic(session, self.topic)
        if arn == None:
            console.fail("Could not create {} SNS toppic".format(self.topic))
            return False
        return True

    def exists(self):
        topics = self.client.list_topics()['Topics']
        for topic in topics:
            if topic['TopicArn'] == self.arn:
                return True
        return False

    def list(self):
        console.info("Subscriptions for {}".format(self.topic))
        subs = self.client.list_subscriptions_by_topic(TopicArn = self.arn)['Subscriptions']
        for sub in subs:
            console.info("    {}".format(sub['Endpoint']))

    def subscribe(self, endpoint, protocol='email'):
        try:
            resp = self.client.subscribe(TopicArn = self.arn,
                                    Protocol = 'email',
                                    Endpoint = address)
        except Exception as ex:
            console.warning("Could not subscribe address {} ({})".format(address, ex))

    def unsubscribe(self, endpoint):
        subs = self.client.list_subscriptions_by_topic(TopicArn = self.arn)['Subscriptions']
        for sub in subs:
            if sub['Endpoint'] == endpoint:
                try:
                    resp = self.client.unsubscribe(SubscriptionArn = sub['SubscriptionArn'])
                except Exception as ex:
                    console.warning("Could not unsubscribe address {} ({})".format(sub['Endpoint'], ex))

class BillingList(SubscriptionList):
    def __init__(self, bosslet_config):
        super().__init__(bosslet_config, bosslet_config.BILLING_TOPIC)
        self.client_cw = bosslet_config.session.client('cloudwatch')

    def get_thresholds(self):
        try:
            thresholds = eval(self.bosslet_config.BILLING_THRESHOLDS)
            console.info("Creating {} billing alarms".format(len(thresholds)))
        except AttributeError: # Assume BILLING_THRESHOLDS is not provided
            console.error("Bosslet value 'BILLING_THRESHOLDS' needs to be defined before creating alarms")
            thresholds = None

        return thresholds

    def exists(self):
        if super().exists() is False:
            return False

        thresholds = self.get_thresholds()
        if thresholds is None:
            return False

        threshold_names = ['Billing_{}'.format(str(t)) for t in thresholds]

        resp = self.client_cw.describe_alarms(AlarmNamePrefix = 'Billing_')
        alarm_names = [a['AlarmName'] for a in resp['MetricAlarms']]

        missing_alarms = 0
        for threshold in thresholds:
            if threshold not in alarm_names:
                missing_alarms += 1

        console.error("Missing {} alarms".format(missing_alarms))

        return missing_alarms == 0

    def create(self):
        if super().create() is False:
            return False

        thresholds = self.get_thresholds()
        if thresholds is None:
            return False

        currency = self.bosslet_config.BILLING_CURRENCY
        alarm_parms = {
            'AlarmName': None,
            'AlarmDescription': None,
            'ActionsEnabled': True,
            'OKActions': [],
            'AlarmActions': [self.arn],
            'InsufficientDataActions': [],
            'MetricName': 'EstimatedCharges',
            'Namespace': 'AWS/Billing',
            'Statistic': 'Maximum',
            'Dimensions': [{'Name': 'Currency', 'Value': currency}],
            'Period': 21600,  # This should be at least 21600 (6 hrs) or all alarms will reset and fire every 6 hrs.
            'EvaluationPeriods': 1,
            'Threshold': None,
            'ComparisonOperator': 'GreaterThanOrEqualToThreshold'
        }

        for threshold in thresholds:
            console.debug("\tAlert level: {:,}".format(threshold))
            alarm_parms['AlarmName'] = "Billing_{}".format(str(threshold))
            alarm_parms['AlarmDescription'] = "Alarm when spending reaches {:,}".format(threshold)
            alarm_parms['Threshold'] = float(threshold)
            response = self.client_cw.put_metric_alarm(**alarm_parms)

class AlertList(SubscriptionList):
    def __init__(self, bosslet_config):
        super().__init__(bosslet_config, bosslet_config.ALERT_TOPIC)


if __name__ == '__main__':
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    parser = configuration.BossParser(description="This script does some initial configuration of a new AWS Account " +
                                                  "to function as theboss.  It should only be run once on an AWS Account.",
                                      formatter_class=argparse.RawDescriptionHelpFormatter,
                                      epilog='one time setup for new AWS Account')
    parser.add_bosslet()
    parser.add_argument('command',
                        choices = ['billing', 'alerts'],
                        help = 'The account setting to configure')
    parser.add_argument('--create',
                        action = 'store_true',
                        help = 'Setup the given setting in the AWS account')
    parser.add_argument('--add',
                        nargs = '+',
                        help = 'Email addresses to add to the target SNS topic')
    parser.add_argument('--rem',
                        nargs = '+',
                        help = 'Email addresses to remove from the target SNS topic')
    parser.add_argument('--ls',
                        action = 'store_true',
                        help = 'List current subscriptions to the target SNS topic')

    args = parser.parse_args()

    if args.command == 'billing':
        list = BillingList(args.bosslet_config)
    elif args.command == 'alerts':
        list = AlertList(args.bosslet_config)

    if args.create:
        if list.exists():
            console.warning("List already exists, not creating")
        else:
            if list.create() is False:
                sys.exit(1)
    elif not list.exists():
        console.error("List doesn't exists, create it first")
        sys.exit(2)

    if args.add:
        for address in args.add:
            list.subscribe(address)

    if args.rem:
        for address in args.rem:
            list.unsubscribe(address)

    if args.ls:
        list.list()

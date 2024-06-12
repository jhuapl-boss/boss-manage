# Copyright 2024 The Johns Hopkins University Applied Physics Laboratory
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

import boto3
import datetime
from dateutil.relativedelta import relativedelta
import argparse

"""
Retreive the last x months of aws bills for the account associated with the aws profile used. 

usage: python3 aws_billing.py myprofile 3
    3 is the number of months to retrieve, including the current one.
    
results:
Total bill for AWS account XXXXXXXXXXXX for the last 3 months:
2024-04-01 to 2024-05-01: $123.71
2024-05-01 to 2024-06-01: $211.22
2024-06-01 to 2024-07-01: $321.90

123.71, $211.22, $321.90

"""

def get_total_bill_for_month(cost_explorer, start_date, end_date, account_id):
    response = cost_explorer.get_cost_and_usage(
        TimePeriod={
            'Start': start_date,
            'End': end_date
        },
        Granularity='MONTHLY',
        Filter={
            'Dimensions': {
                'Key': 'LINKED_ACCOUNT',
                'Values': [account_id]
            }
        },
        Metrics=['UnblendedCost']
    )
    total = response['ResultsByTime'][0]['Total']['UnblendedCost']['Amount']
    return float(total)


def get_account_id(sts_client):
    response = sts_client.get_caller_identity()
    return response['Account']


def main(profile, months):
    # Create a session using the specified profile
    session = boto3.Session(profile_name=profile)
    sts_client = session.client('sts')
    cost_explorer = session.client('ce')

    account_id = get_account_id(sts_client)
    monthly_dollars = []

    now = datetime.datetime.now()
    end_date = datetime.datetime(now.year, now.month, 1) + relativedelta(
        months=1)  # gets the beginning of the next month.
    # now.replace(day=1)
    start_date = end_date - relativedelta(months=months)

    print(f"Total bill for AWS account {account_id} for the last {months} months:")
    for i in range(months):
        current_start = start_date + relativedelta(months=i)
        current_end = current_start + relativedelta(months=1)

        start_str = current_start.strftime('%Y-%m-%d')
        end_str = current_end.strftime('%Y-%m-%d')

        total = get_total_bill_for_month(cost_explorer, start_str, end_str, account_id)
        print(f"{start_str} to {end_str}: ${total:.2f}")
        monthly_dollars.append(f"${total:.2f}")

    month_list = ", ".join(monthly_dollars)
    print()
    print(month_list)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Get AWS monthly billing for the last x months.')
    parser.add_argument('profile', type=str, help='The AWS profile name')
    parser.add_argument('months', type=int, help='The number of months to retrieve the billing for')

    args = parser.parse_args()
    main(args.profile, args.months)

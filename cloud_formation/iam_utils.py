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
"""Sandy's script to get testing """

import argparse
import sys
import os
import boto3
import json
from boto3 import Session
from botocore.exceptions import ClientError
import hosts
# import library as lib
import pprint
import datetime
import ast

IAM_CONFIG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", "iam"))
DEFAULT_POLICY_FILE = os.path.join(IAM_CONFIG_DIR, "policies.json")
DEFAULT_GROUP_FILE = os.path.join(IAM_CONFIG_DIR, "groups.json")
DEFAULT_ROLES_FILE = os.path.join(IAM_CONFIG_DIR, "roles.json")

class IamUtils:


    def __init__(self, session):
        self.session = session
        self.iam_details = None
        self.policy_keyword_filters = ["-client-policy-"]  # Any keywords in the policy name should be skipped.
        self.policy_whole_filters = ["gion-test-policy", "aplAllowAssumeRoleInProduction", "aplDenyAssumeRoleInProduction"]
        self.policies = []
        self.groups = []
        self.roles = []
        os.makedirs(IAM_CONFIG_DIR, exist_ok=True)

    def get_iam_details(self):
        client = self.session.client('iam')
        self.iam_details = client.get_account_authorization_details(MaxItems=1000, Filter=['Role','Group',
                                                                                           'LocalManagedPolicy'])
        iam_parts = ['UserDetailList', 'RoleDetailList', 'Policies', 'GroupDetailList']
        next_batch = self.iam_details
        while next_batch['IsTruncated']:
            next_batch = client.get_account_authorization_details(MaxItems=1000, Marker=next_batch['Marker'],
                                                                  Filter=['Role','Group', 'LocalManagedPolicy'])
            for part in iam_parts:
                self.iam_details[part].extend(next_batch[part])
        self.iam_details['IsTruncated'] = False
        if 'Marker' in self.iam_details: del self.iam_details['Marker']

    def save_iam_details(self, filename="iam_details.json"):
        with open(filename, 'w') as f:
            pprint.pprint(self.iam_details, f)

    def filter(self, name_field, keyword_filters, whole_filters, item_to_filter):
        for keyword in keyword_filters:
            if keyword in item_to_filter[name_field]:
                return True
        if item_to_filter[name_field] in whole_filters:
            return True
        return False

    def extract_policies_from_iam_details(self):
        policy_temp_list = []
        for policy in self.iam_details["Policies"]:
            if self.filter("PolicyName", self.policy_keyword_filters, self.policy_whole_filters, policy):
                print("filtering: " + policy["PolicyName"])
                continue

            for versions in policy['PolicyVersionList']:
                if versions['IsDefaultVersion']:
                    # Description is not currently in the response even though it is in the docs.
                    # so we do this test if it doesn't exist.
                    new_policy = {'PolicyName': policy['PolicyName'],
                                  'Path': policy['Path'],
                                  'PolicyDocument': json.dumps(versions['Document'])}
                    if 'Description' in policy:
                        new_policy["Description"] = policy["Description"]
                    policy_temp_list.append(new_policy)
                    break

        policy_string = json.dumps(policy_temp_list, indent=4)
        account_switched_policy = policy_string.replace(hosts.DEV_ACCOUNT, hosts.PROD_ACCOUNT)
        self.policies = json.loads(account_switched_policy)

    def save_policies(self, filename):
        with open(filename, 'w') as f:
            json.dump(self.policies, f, indent=4)

    def import_policies_to_aws(self, use_assume_role=True):
        if len(self.policies) == 0:
            print("No polices to import yet.")
            return

        if use_assume_role:
            import_session = assume_production_role(self.session)
        else:
            import_session = self.session
        for policy in self.policies:
            client = import_session.client('iam')
            try:
                client.create_policy(**policy)
            except ClientError as e:
                if e.response['Error']['Code'] == 'EntityAlreadyExists':
                    print("Policy {} already exists cannot load again.".format(policy["PolicyName"]))
                else:
                    print("error occur creating policy: {}".format(policy["PolicyName"]))
                    print("   Details: {}".format(str(e)))

    def load_policies_from_file(self, filename):
        with open(filename, 'r') as f:
            self.policies = json.load(f)

    def print_alarms(self, filename=None):
        client = self.session.client("cloudwatch")
        response = client.describe_alarms(
            MaxRecords=100
        )
        pprint.pprint(response)

    def export_to_files(self):
        self.get_iam_details()

        self.extract_policies_from_iam_details()
        self.save_policies(DEFAULT_POLICY_FILE)

    def load_from_files(self):
        self.load_policies_from_file(DEFAULT_POLICY_FILE)


def assume_production_role(session):
    sts_client = session.client('sts')
    assumed_role_object = sts_client.assume_role(
        RoleArn="arn:aws:iam::451493790433:role/DeveloperAccess",
        RoleSessionName="AssumeRoleSession5"
    )
    credentials = assumed_role_object['Credentials']

    # Use the temporary credentials create a new session object.
    print("region: " + str(session))
    print("assumed creds: " + str(credentials))
    production_session = boto3.Session(aws_access_key_id=credentials["AccessKeyId"],
                                       aws_secret_access_key=credentials["SecretAccessKey"],
                                       aws_session_token=credentials["SessionToken"],
                                       region_name='us-east-1')
    return production_session

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

    parser = argparse.ArgumentParser(description="Request SSL domain certificates for theboss.io subdomains",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog='create domain cert')
    parser.add_argument("--aws-credentials", "-a",
                        metavar="<file>",
                        default=os.environ.get("AWS_CREDENTIALS"),
                        type=argparse.FileType('r'),
                        help="File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    credentials = json.load(args.aws_credentials)
    session = create_session(credentials)

    iam = IamUtils(session)
    print("Exporting..")
    iam.export_to_files()
    iam.load_from_files()
    print("Importing..")
    iam.import_policies_to_aws()

    #export.save_alarms()


    # with open("/home/hiderrt1/iam_details.pprint.txt", 'r', encoding="utf-8") as f:
    #     results = json.load(f, encoding="utf-8")

    # with open(filename, 'w') as f:
    #     json.dump(iam_details, f, indent=4)



        # for policy in iam_details['Policies']:
    #     for version in policy['PolicyVersionList']:
    #         if version['IsDefaultVersion']:
    #             pprint.pprint(version)
    #             print()
    #             print()



    # response = client.create_policy(
    #     PolicyName='string',
    #     Path='string',
    #     PolicyDocument='string',
    #     Description='string'
    # )


    # result = hosts.BASE_DOMAIN_CERTS["proyer.boss"]
    # print(result)

    # results = lib.set_domain_to_dns_name(session, 'auth.hiderrt1.theboss.io',
    #                            'elb-auth-hiderrt1-boss-1659397297.us-east-1.elb.amazonaws.com')
    # pp = pprint.PrettyPrinter()
    # pp.pprint(results)

    # domain = "hiderrt1.boss"
    # if domain in hosts.BASE_DOMAIN_CERTS.keys():
    #     print(hosts.BASE_DOMAIN_CERTS[domain])
    # else:
    #     print('not found')
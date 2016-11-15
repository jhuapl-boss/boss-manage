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

"""IAM Utils script.  Used to pull roles, policies, instance_policies, groups
from Developer account into Production Account

Currently setup to assume DeveloperAccess role in Production Account.
Could also be used with Production Credentials to import from text files.

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
DEFAULT_POLICY_FILE = os.path.join(IAM_CONFIG_DIR, "policies.json")
DEFAULT_GROUP_FILE = os.path.join(IAM_CONFIG_DIR, "groups.json")
DEFAULT_ROLES_FILE = os.path.join(IAM_CONFIG_DIR, "roles.json")
DEFAULT_INSTANCE_PROFILES_FILE = os.path.join(IAM_CONFIG_DIR, "instance_profiles.json")
DEFAULT_INSTANCE_PROFILE_ROLES_FILE = os.path.join(IAM_CONFIG_DIR, "instance_profile_roles.json")
DEFAULT_ROLE_MANAGED_POLICIES_FILE = os.path.join(IAM_CONFIG_DIR, "role_managed_policies.json")
DEFAULT_ROLE_INLINE_POLICIES_FILE = os.path.join(IAM_CONFIG_DIR, "role_inline_policies.json")
DEFAULT_GROUP_MANAGED_POLICIES_FILE = os.path.join(IAM_CONFIG_DIR, "group_managed_policies.json")
DEFAULT_GROUP_INLINE_POLICIES_FILE = os.path.join(IAM_CONFIG_DIR, "group_inline_policies.json")
DEFAULT_CF_TEMPLATE = os.path.join(IAM_CONFIG_DIR, "cf_template.json")

class IamUtils:

    def __init__(self, session):
        self.session = session
        self.iam_details = None
        self.policy_keyword_filters = ["-client-policy-"]  # Any keywords in the policy name should be skipped.
        self.policy_whole_filters = ["gion-test-policy", "aplAllowAssumeRoleInProduction",
                                     "aplDenyAssumeRoleInProduction"]
        self.role_keyword_filters = []
        self.role_whole_filters = []
        self.group_keyword_filters = []
        self.group_whole_filters = ["aplSpeedTestGroup", " aplAdminGroup",  "aplDenyProductionAccountAccess",
                                    "aplProductionAccountAccess"]
        self.policies = []
        self.groups = []
        self.roles = []
        self.instance_profiles = []
        self.instance_profile_roles = []
        self.role_managed_polices = []
        self.role_inline_policies = []
        self.group_managed_polices = []
        self.group_inline_policies = []
        os.makedirs(IAM_CONFIG_DIR, exist_ok=True)

    def to_prod_account(self, list):
        current_account = lib.get_account_id_from_session(self.session)
        if current_account != hosts.PROD_ACCOUNT:
            return self.swap_accounts(list, current_account, hosts.PROD_ACCOUNT)
        else:
            return list

    def to_sessions_account(self, list):
        current_account = lib.get_account_id_from_session()
        if current_account != hosts.PROD_ACCOUNT:
            return self.swap_accounts(list, hosts.PROD_ACCOUNT, current_account)
        else:
            return list

    def swap_accounts(self, list, from_acc, to_acc):
        list_string = json.dumps(list, indent=4)
        account_switched = list_string.replace(from_acc, to_acc)
        return json.loads(account_switched)

    def get_iam_details_from_aws(self):
        client = self.session.client('iam')
        self.iam_details = client.get_account_authorization_details(MaxItems=1000, Filter=['Role', 'Group',
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

    def extract_policies_from_iam_details(self, for_cf=False):
        """
        extracts policies from the iam details.
        Args:
            for_cf: True if extracting for cloud formation template

        Returns:

        """
        policy_temp_list = []
        for policy in self.iam_details["Policies"]:
            if self.filter("PolicyName", self.policy_keyword_filters, self.policy_whole_filters, policy):
                print("filtering: " + policy["PolicyName"])
                continue

            for versions in policy['PolicyVersionList']:
                if versions['IsDefaultVersion']:
                    # Description is not currently in the response even though it is in the docs.
                    # so we do this test if it doesn't exist.
                    policy_doc = versions['Document'] if for_cf else json.dumps(versions['Document'], indent=2)
                    new_policy = {'PolicyName': policy['PolicyName'],
                                  'Path': policy['Path'],
                                  'PolicyDocument': policy_doc}
                    if 'Description' in policy:
                        new_policy["Description"] = policy["Description"]
                    policy_temp_list.append(new_policy)
                    break

        self.policies = self.to_prod_account(policy_temp_list)

    def save_policies(self, filename):
        with open(filename, 'w') as f:
            json.dump(self.policies, f, indent=4)

    def import_policies_to_aws(self, use_assume_role=False):
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

    def extract_roles_from_iam_details(self, for_cf=False):
        role_temp_list = []
        managed_pol_role_list = []
        inst_pol_role_list = []
        for role in self.iam_details["RoleDetailList"]:
            if self.filter("RoleName", self.role_keyword_filters, self.role_whole_filters, role):
                print("filtering: " + role["RoleName"])
                continue
            policy_doc = role['AssumeRolePolicyDocument'] if for_cf else json.dumps(role['AssumeRolePolicyDocument'],
                                                                                    indent=2)
            new_role = {'RoleName': role['RoleName'],
                        'Path': role['Path'],
                        'AssumeRolePolicyDocument': policy_doc}
            role_temp_list.append(new_role)
            client = self.session.client("iam")

            for mp_pol in role["AttachedManagedPolicies"]:
                mp_pol["RoleName"] = role["RoleName"]
                if "PolicyName" in mp_pol:
                    del mp_pol["PolicyName"]
                managed_pol_role_list.append(mp_pol)

            for inst_pol in role["RolePolicyList"]:
                inst_pol["RoleName"] = role["RoleName"]
                doc = inst_pol['PolicyDocument']
                inst_pol['PolicyDocument'] = doc if for_cf else json.dumps(doc, indent=2)
                inst_pol_role_list.append(inst_pol)

        self.roles = self.to_prod_account(role_temp_list)
        self.role_managed_polices = self.to_prod_account(managed_pol_role_list)
        self.role_inline_policies = self.to_prod_account(inst_pol_role_list)

    def save_roles(self, filename):
        with open(filename, 'w') as f:
            json.dump(self.roles, f, indent=4)

    def load_roles_from_file(self, filename):
        with open(filename, 'r') as f:
            self.roles = json.load(f)

    def save_role_managed_policies(self, filename):
        with open(filename, 'w') as f:
            json.dump(self.role_managed_polices, f, indent=4)

    def load_role_managed_policies_from_file(self, filename):
        with open(filename, 'r') as f:
            self.role_managed_polices = json.load(f)

    def save_role_inline_policies(self, filename):
        with open(filename, 'w') as f:
            json.dump(self.role_inline_policies, f, indent=4)

    def load_role_inline_policies_from_file(self, filename):
        with open(filename, 'r') as f:
            self.role_inline_policies = json.load(f)

    def import_roles_to_aws(self, use_assume_role=False):
        if use_assume_role:
            import_session = assume_production_role(self.session)
        else:
            import_session = self.session
        for role in self.roles:
            client = import_session.client('iam')
            try:
                client.create_role(**role)
            except ClientError as e:
                if e.response['Error']['Code'] == 'EntityAlreadyExists':
                    print("Role {} already exists cannot load again.".format(role["RoleName"]))
                else:
                    print("error occur creating role: {}".format(role["RoleName"]))
                    print("   Details: {}".format(str(e)))

    def import_role_managed_policies_to_aws(self, use_assume_role=False):
        if use_assume_role:
            import_session = assume_production_role(self.session)
        else:
            import_session = self.session
        for mp in self.role_managed_polices:
            client = import_session.client('iam')
            try:
                client.attach_role_policy(**mp)
            except ClientError as e:
                if e.response['Error']['Code'] == 'EntityAlreadyExists':
                    print("Role Managed Policy {} - {} already exists cannot load again.".format(mp["RoleName"],
                                                                                                 mp["PolicyArn"]))
                else:
                    print("error occur creating role managed policy: {} - {}".format(mp["RoleName"], mp["PolicyArn"]))
                    print("   Details: {}".format(str(e)))

    def import_role_inline_policies_to_aws(self, use_assume_role=False):
        if use_assume_role:
            import_session = assume_production_role(self.session)
        else:
            import_session = self.session
        for ip in self.role_inline_policies:
            client = import_session.client('iam')
            try:
                client.put_role_policy(**ip)
            except ClientError as e:
                if e.response['Error']['Code'] == 'EntityAlreadyExists':
                    print("Role Inline Policy {} - {} already exists cannot load again.".format(ip["RoleName"],
                                                                                                 ip["PolicyName"]))
                else:
                    print("error occur creating role inline policy: {} - {}".format(ip["RoleName"], ip["PolicyName"]))
                    print("   Details: {}".format(str(e)))

    def get_instance_profiles_from_aws(self):
        client = self.session.client('iam')
        response = client.list_instance_profiles(MaxItems=1000)
        ip_list = response["InstanceProfiles"]
        batch = response
        while batch["IsTruncated"]:
            batch = client.list_instance_profiles(MaxItems=1000)
            ip_list.append(batch["InstanceProfiles"])

        temp_ip_list = []
        ip_roles_list = []
        for ip in ip_list:
            new_ip = {"InstanceProfileName": ip["InstanceProfileName"],
                      "Path":  ip["Path"]}
            temp_ip_list.append(new_ip)
            for role in ip["Roles"]:
                new_ip_role = {"InstanceProfileName": ip["InstanceProfileName"],
                               "RoleName": role["RoleName"]}
                ip_roles_list.append(new_ip_role)
        self.instance_profiles = temp_ip_list
        self.instance_profile_roles = ip_roles_list

    def save_instance_profiles(self, filename):
        with open(filename, 'w') as f:
            json.dump(self.instance_profiles, f, indent=4)

    def load_instance_profile_from_file(self, filename):
        with open(filename, 'r') as f:
            self.instance_profiles = json.load(f)

    def save_instance_profile_roles(self, filename):
        with open(filename, 'w') as f:
            json.dump(self.instance_profile_roles, f, indent=4)

    def load_instance_profile_roles_from_file(self, filename):
        with open(filename, 'r') as f:
            self.instance_profile_roles = json.load(f)

    def import_instance_profiles_to_aws(self, use_assume_role=False):
        if use_assume_role:
            import_session = assume_production_role(self.session)
        else:
            import_session = self.session
        for ip in self.instance_profiles:
            client = import_session.client('iam')
            try:
                client.create_instance_profile(**ip)
            except ClientError as e:
                if e.response['Error']['Code'] == 'EntityAlreadyExists':
                    print("Instance_Profile {} already exists cannot load again.".format(ip["InstanceProfileName"]))
                else:
                    print("error occur creating instance profile: {}".format(ip["InstanceProfileName"]))
                    print("   Details: {}".format(str(e)))

    def import_instance_profiles_roles_to_aws(self, use_assume_role=False):
        if use_assume_role:
            import_session = assume_production_role(self.session)
        else:
            import_session = self.session
        for ip_role in self.instance_profile_roles:
            client = import_session.client('iam')
            try:
                client.add_role_to_instance_profile(**ip_role)
            except ClientError as e:
                if e.response['Error']['Code'] == 'EntityAlreadyExists':
                    print("Instance_Profile_Role {} - {} already exists cannot load again."
                          .format(ip_role["InstanceProfileName"], ip_role["RoleName"]))
                else:
                    print("error occur creating instance profile role: {} - {}".format(ip_role["InstanceProfileName"],
                                                                                       ip_role["RoleName"]))
                    print("   Details: {}".format(str(e)))

    def extract_groups_from_iam_details(self, for_cf=False):
        group_temp_list = []
        managed_pol_group_list = []
        inst_pol_group_list = []
        for group in self.iam_details["GroupDetailList"]:
            if self.filter("GroupName", self.group_keyword_filters, self.group_whole_filters, group):
                print("filtering: " + group["GroupName"])
                continue

            new_group = {'GroupName': group['GroupName'],
                        'Path': group['Path']}
            group_temp_list.append(new_group)
            client = self.session.client("iam")

            for mp_pol in group["AttachedManagedPolicies"]:
                mp_pol["GroupName"] = group["GroupName"]
                if "PolicyName" in mp_pol:
                    del mp_pol["PolicyName"]
                managed_pol_group_list.append(mp_pol)

            for inst_pol in group["GroupPolicyList"]:
                inst_pol["GroupName"] = group["GroupName"]
                doc = inst_pol['PolicyDocument']
                inst_pol['PolicyDocument'] = doc if for_cf else json.dumps(doc, indent=2)
                inst_pol_group_list.append(inst_pol)

        self.groups = self.to_prod_account(group_temp_list)
        self.group_managed_polices = self.to_prod_account(managed_pol_group_list)
        self.group_inline_policies = self.to_prod_account(inst_pol_group_list)

    def save_groups(self, filename):
        with open(filename, 'w') as f:
            json.dump(self.groups, f, indent=4)

    def load_groups_from_file(self, filename):
        with open(filename, 'r') as f:
            self.groups = json.load(f)

    def save_group_managed_policies(self, filename):
        with open(filename, 'w') as f:
            json.dump(self.group_managed_polices, f, indent=4)

    def load_group_managed_policies_from_file(self, filename):
        with open(filename, 'r') as f:
            self.group_managed_polices = json.load(f)

    def save_group_inline_policies(self, filename):
        with open(filename, 'w') as f:
            json.dump(self.group_inline_policies, f, indent=4)

    def load_group_inline_policies_from_file(self, filename):
        with open(filename, 'r') as f:
            self.group_inline_policies = json.load(f)

    def import_groups_to_aws(self, use_assume_role=True):
        if use_assume_role:
            import_session = assume_production_role(self.session)
        else:
            import_session = self.session
        for group in self.groups:
            client = import_session.client('iam')
            try:
                client.create_group(**group)
            except ClientError as e:
                if e.response['Error']['Code'] == 'EntityAlreadyExists':
                    print("Group {} already exists cannot load again.".format(group["GroupName"]))
                else:
                    print("error occur creating group: {}".format(group["GroupName"]))
                    print("   Details: {}".format(str(e)))

    def import_group_managed_policies_to_aws(self, use_assume_role=True):
        if use_assume_role:
            import_session = assume_production_role(self.session)
        else:
            import_session = self.session
        for mp in self.group_managed_polices:
            client = import_session.client('iam')
            try:
                client.attach_group_policy(**mp)
            except ClientError as e:
                if e.response['Error']['Code'] == 'EntityAlreadyExists':
                    print("Group Managed Policy {} - {} already exists cannot load again.".format(
                        mp["GroupName"],
                        mp["PolicyArn"]))
                else:
                    print("error occur creating group managed policy: {} - {}".format(mp["GroupName"],
                                                                                     mp["PolicyArn"]))
                    print("   Details: {}".format(str(e)))

    def import_group_inline_policies_to_aws(self, use_assume_role=True):
        if use_assume_role:
            import_session = assume_production_role(self.session)
        else:
            import_session = self.session
        for ip in self.group_inline_policies:
            client = import_session.client('iam')
            try:
                client.put_group_policy(**ip)
            except ClientError as e:
                if e.response['Error']['Code'] == 'EntityAlreadyExists':
                    print("Group Inline Policy {} - {} already exists cannot load again.".format(
                        ip["GroupName"],
                        ip["PolicyName"]))
                else:
                    print("error occur creating group inline policy: {} - {}".format(ip["GroupName"],
                                                                                    ip["PolicyName"]))
                    print("   Details: {}".format(str(e)))

    def print_alarms(self, filename=None):
        client = self.session.client("cloudwatch")
        response = client.describe_alarms(
            MaxRecords=100
        )
        pprint.pprint(response)

    def export_to_files(self):
        self.get_iam_details_from_aws()

        self.extract_policies_from_iam_details()
        self.save_policies(DEFAULT_POLICY_FILE)

        self.extract_roles_from_iam_details()
        self.save_roles(DEFAULT_ROLES_FILE)
        self.save_role_managed_policies(DEFAULT_ROLE_MANAGED_POLICIES_FILE)
        self.save_role_inline_policies(DEFAULT_ROLE_INLINE_POLICIES_FILE)

        self.get_instance_profiles_from_aws()
        self.save_instance_profiles(DEFAULT_INSTANCE_PROFILES_FILE)
        self.save_instance_profile_roles(DEFAULT_INSTANCE_PROFILE_ROLES_FILE)

        self.extract_groups_from_iam_details()
        self.save_groups(DEFAULT_GROUP_FILE)
        self.save_group_managed_policies(DEFAULT_GROUP_MANAGED_POLICIES_FILE)
        self.save_group_inline_policies(DEFAULT_GROUP_INLINE_POLICIES_FILE)

    def load_from_files(self):
        self.load_policies_from_file(DEFAULT_POLICY_FILE)
        self.load_roles_from_file(DEFAULT_ROLES_FILE)
        self.load_instance_profile_from_file(DEFAULT_INSTANCE_PROFILES_FILE)
        self.load_instance_profile_roles_from_file(DEFAULT_INSTANCE_PROFILE_ROLES_FILE)
        self.load_role_managed_policies_from_file(DEFAULT_ROLE_MANAGED_POLICIES_FILE)
        self.load_role_inline_policies_from_file(DEFAULT_ROLE_INLINE_POLICIES_FILE)
        self.load_groups_from_file(DEFAULT_GROUP_FILE)
        self.load_group_managed_policies_from_file(DEFAULT_GROUP_MANAGED_POLICIES_FILE)
        self.load_group_inline_policies_from_file(DEFAULT_GROUP_INLINE_POLICIES_FILE)

    def import_to_aws(self, use_assume_role=False):
        self.import_policies_to_aws(use_assume_role)
        self.import_roles_to_aws(use_assume_role)
        self.import_instance_profiles_to_aws(use_assume_role)
        self.import_instance_profiles_roles_to_aws(use_assume_role)
        self.import_role_inline_policies_to_aws(use_assume_role)
        self.import_role_managed_policies_to_aws(use_assume_role)
        self.import_groups_to_aws(use_assume_role)
        self.import_group_managed_policies_to_aws(use_assume_role)
        self.import_group_inline_policies_to_aws(use_assume_role)

    def delete_policies(self,  use_assume_role=False):
        if use_assume_role:
            import_session = assume_production_role(self.session)
        else:
            import_session = self.session
        acc = lib.get_account_id_from_session(import_session)
        while input("Your about to delete all policies from account {}.  type yes to continue: ".format(acc)) != 'yes':
            pass
        client = import_session.client('iam')
        policies = client.list_policies(Scope='Local')
        for policy in policies["Policies"]:
            print("deleting " + policy["PolicyName"])
            client.delete_policy(PolicyArn=policy["Arn"])



def assume_production_role(session):

    sts_client = session.client('sts')
    role_arn = "arn:aws:iam::{}:role/DeveloperAccess".format(hosts.PROD_ACCOUNT)
    assumed_role_object = sts_client.assume_role(
        RoleArn=role_arn,
        RoleSessionName="AssumeRoleSession5"
    )
    credentials = assumed_role_object['Credentials']

    # Use the temporary credentials create a new session object.
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

    parser = argparse.ArgumentParser(description="Exports Iam information from Dev Account to Production Account.  Assume role must be active.",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog='Exports and Imports Iam Information')
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
    #iam.export_to_cf_template()


    #iam.get_iam_details_from_aws()

    print("Exporting..")
    iam.export_to_files()

    #iam.load_from_files()
    #print("Importing..")
    #iam.import_to_aws(use_assume_role=False)

    #iam.delete_policies()  # be careful with this one.


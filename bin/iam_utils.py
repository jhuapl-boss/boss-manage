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
Several methods have use_assume_role option for the developerAccess to assume
production account access.  The preferable way is to use production credentials
directly.

The following variables have to be converted from JSON to a String before using in Boto3
Policy.PolicyDocument


"""

import argparse
import sys
import os
import pprint
import datetime
import json

from boto3 import Session
from botocore.exceptions import ClientError

import alter_path
from lib import aws
from lib import utils
from lib import hosts
from lib import constants as const
from lib.boto_wrapper import IamWrapper as iw

IAM_CONFIG_DIR = const.repo_path("config", "iam")
DEFAULT_POLICY_FILE = os.path.join(IAM_CONFIG_DIR, "policies.json")
DEFAULT_GROUP_FILE = os.path.join(IAM_CONFIG_DIR, "groups.json")
DEFAULT_ROLES_FILE = os.path.join(IAM_CONFIG_DIR, "roles.json")
COMMANDS=["import", "export"]

class IamUtils:
    def __init__(self, session):
        self.session = session
        self.iam_details = None
        self.iw = iw(session.client("iam"))
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
        os.makedirs(IAM_CONFIG_DIR, exist_ok=True)

    def to_prod_account(self, list):
        current_account = aws.get_account_id_from_session(self.session)
        if current_account != hosts.PROD_ACCOUNT:
            return self.swap_accounts(list, current_account, hosts.PROD_ACCOUNT)
        else:
            return list

    def to_sessions_account(self, list):
        current_account = aws.get_account_id_from_session(self.session)  # TODO SH this only works after we remove possible assume account
        if current_account != hosts.PROD_ACCOUNT:
            return self.swap_accounts(list, hosts.PROD_ACCOUNT, current_account)
        else:
            return list

    def swap_accounts(self, list, from_acc, to_acc):
        list_string = json.dumps(list, indent=2)
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

    def extract_policies_from_iam_details(self):
        """
        extracts policies from the iam details.

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
                    policy_doc = versions['Document']
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
            json.dump(self.policies, f, indent=2, sort_keys=True)

    def adjust_policies_in_aws(self, use_assume_role=False):
        '''
        Adjusts the AWS policies to match the current in memory policies. It creates the polices if
        they do not exist in AWS and updates the policy version active policy version to match the
        loaded policy version.  It will not delete any policies. It cannot not adjust the policy path but
        will inform if the policy path is different.
        Args:
            use_assume_role: set to True if using developer account credentials and plan to assume production credentials

        Returns:

        '''
        if use_assume_role:
            import_session = assume_production_role(self.session)
        else:
            import_session = self.session
        if self.iam_details == None:
            print("iam_details must be imported first.")
            return
        for policy in self.policies:
            client = import_session.client('iam')
            boto3_policy = policy.copy()

            aws_policy = utils.find_dict_with(self.iam_details["Policies"], "PolicyName",  boto3_policy["PolicyName"])
            if aws_policy is None:
                try:
                    boto3_policy["PolicyDocument"] = json.dumps(boto3_policy["PolicyDocument"], indent=2, sort_keys=True)
                    client.create_policy(**boto3_policy)
                except ClientError as e:
                    if e.response['Error']['Code'] == 'EntityAlreadyExists':
                        print("Policy {} already exists cannot load again.".format(boto3_policy["PolicyName"]))
                    else:
                        print("error occur creating policy: {}".format(boto3_policy["PolicyName"]))
                        print("   Details: {}".format(str(e)))
            else:
                self.validate_policy(client, boto3_policy, aws_policy)

    def validate_policy(self, client, mem_pol, aws_pol):
        if mem_pol["PolicyName"] != aws_pol["PolicyName"]:
            print("Cannot validate different Policys: {} and {}".format(mem_pol["PolicyName"], aws_pol["PolicyName"]))
            return
        if mem_pol["Path"] != aws_pol["Path"]:
            print("WARNING Paths differ for policy {}: Path_In_File={} Path_In_AWS={}".format(mem_pol["PolicyName"],
                                                                                              mem_pol["Path"],
                                                                                              aws_pol["Path"]))
            print("You will need to manually delete the old policy for the Path to be changed.")
        aws_ver = get_default_policy_version(aws_pol)
        mem_pol["PolicyDocument"] = json.dumps(mem_pol["PolicyDocument"], indent=2, sort_keys=True)
        aws_ver["Document"] = json.dumps(aws_ver["Document"], indent=2, sort_keys=True)
        if mem_pol["PolicyDocument"] != aws_ver["Document"]:
            print("Default Policy version differs")
            if len(aws_pol["PolicyVersionList"]) == 5:
                response = client.delete_policy_version(PolicyArn=aws_pol["Arn"],
                                                        VersionId=get_oldest_policy_version(aws_pol))
            client.create_policy_version(PolicyArn=aws_pol['Arn'],
                                         PolicyDocument=mem_pol["PolicyDocument"],
                                         SetAsDefault=True)

    def load_policies_from_file(self, filename):
        with open(filename, 'r') as f:
            self.policies = json.load(f)

    def extract_roles_from_iam_details(self):
        role_temp_list = []
        for role in self.iam_details["RoleDetailList"]:
            managed_pol_list = []
            inst_pol_role_list = []
            inst_profile_list = []
            if self.filter("RoleName", self.role_keyword_filters, self.role_whole_filters, role):
                print("filtering: " + role["RoleName"])
                continue
            new_role = {'RoleName': role['RoleName'],
                        "Path": role["Path"],
                        'AssumeRolePolicyDocument': role['AssumeRolePolicyDocument']}

            for mp_pol in role["AttachedManagedPolicies"]:
                managed_pol_list.append(mp_pol["PolicyArn"])
            new_role["AttachedManagedPolicies"] = managed_pol_list

            for inst_pol in role["RolePolicyList"]:
                inst_pol_role_list.append(inst_pol)
            new_role["RolePolicyList"] = inst_pol_role_list

            for inst_profile in role["InstanceProfileList"]:
                new_inst_pro = {"InstanceProfileName": inst_profile["InstanceProfileName"],
                                "Path": inst_profile["Path"]}
                inst_profile_list.append(new_inst_pro)
            new_role["InstanceProfileList"] =inst_profile_list
            role_temp_list.append(new_role)
        self.roles = self.to_prod_account(role_temp_list)

    def create_full_role(self, role):
        assume_role_pol_doc_str = json.dumps(role["AssumeRolePolicyDocument"], indent=2, sort_keys=True)
        self.iw.create_role(role["RoleName"], role["Path"], assume_role_pol_doc_str)
        for inline_pol in role["RolePolicyList"]:
            self.iw.put_role_policy(role["RoleName"], inline_pol["PolicyName"], inline_pol["PolicyDocument"])
        for mngd_pol_arn in role["AttachedManagedPolicies"]:
            self.iw.attach_role_policy(role["RoleName"], mngd_pol_arn)
        for inst_profile in role["InstanceProfileList"]:
            self.iw.create_instance_profile(inst_profile["InstanceProfileName"], inst_profile["Path"])
            self.iw.add_role_to_instance_profile(role["RoleName"], inst_profile["InstanceProfileName"])

    def adjust_roles_in_aws(self, use_assume_role=False):
        '''
        Adjusts the AWS roles to match the current in memory roles. It creates the roles if
        they do not exist in AWS.  Also adjusts attached managed policies and inline policies associated with the role
        and the Assume Policy Document.
         It will not delete any roles.
        Args:
            use_assume_role: set to True if using developer account credentials and plan to assume production credentials

        Returns:

        '''
        if use_assume_role:
            import_session = assume_production_role(self.session)
        else:
            import_session = self.session
        if self.iam_details == None:
            print("iam_details must be imported first.")
            return
        for role in self.roles:
            client = import_session.client('iam')
            aws_role = utils.find_dict_with(self.iam_details["RoleDetailList"], "RoleName",  role["RoleName"])
            if aws_role is None:
                self.create_full_role(role)
            else:
                self.validate_role(client, role, aws_role)

    def validate_role(self, client, mem_role, aws_role):
        if mem_role["RoleName"] != aws_role["RoleName"]:
            print("Cannot validate different Roles: {} and {}".format(mem_role["RoleName"], aws_role["RoleName"]))
            return
        if mem_role["Path"] != aws_role["Path"]:
            print("WARNING Paths differ for role {}: Path_In_File={} Path_In_AWS={}".format(mem_role["RoleName"],
                                                                                             mem_role["Path"],
                                                                                             aws_role["Path"]))
            print("You will need to manually delete the old role for the Path to be changed.")

        mem_assume_pol_str = json.dumps(mem_role["AssumeRolePolicyDocument"], indent=2, sort_keys=True)
        aws_assume_pol_str = json.dumps(aws_role["AssumeRolePolicyDocument"], indent=2, sort_keys=True)
        if mem_assume_pol_str != aws_assume_pol_str:
            self.iw.update_assume_role_policy(mem_role["RoleName"], mem_role["AssumeRolePolicyDocument"])

        for inline_pol in mem_role["RolePolicyList"]:
            aws_inline_pol = utils.find_dict_with(aws_role["RolePolicyList"], "PolicyName", inline_pol["PolicyName"])
            if aws_inline_pol is None:
                self.iw.put_role_policy(mem_role["RoleName"], inline_pol["PolicyName"], inline_pol["PolicyDocument"])
                continue
            aws_doc_str = json.dumps(aws_inline_pol["PolicyDocument"], indent=2, sort_keys=True)
            mem_doc_str = json.dumps(inline_pol["PolicyDocument"], indent=2, sort_keys=True)
            if mem_doc_str != aws_doc_str:
                self.iw.put_role_policy(mem_role["RoleName"], inline_pol["PolicyName"], inline_pol["PolicyDocument"])
        for aws_inline_pol in aws_role["RolePolicyList"]:
            matching_mem_pol = utils.find_dict_with(mem_role["RolePolicyList"], "PolicyName", aws_inline_pol["PolicyName"])
            if matching_mem_pol is None:
                # AWS has a policy that is not in memory version, it should be deleted.
                self.iw.delete_role_policy(mem_role["RoleName"], aws_inline_pol["PolicyName"])

        for mngd_pol_arn in mem_role["AttachedManagedPolicies"]:
            self.iw.attach_role_policy(mem_role["RoleName"], mngd_pol_arn)
        for aws_mngd_pol in aws_role["AttachedManagedPolicies"]:
            if aws_mngd_pol["PolicyArn"] not in mem_role["AttachedManagedPolicies"]:
                # AWS has a mngd policy that is not in memory version, it should be deleted.
                self.iw.detach_role_policy(mem_role["RoleName"], aws_mngd_pol["PolicyArn"])

        for inst_pro in mem_role["InstanceProfileList"]:
            aws_inst_pro = utils.find_dict_with(aws_role["InstanceProfileList"], "InstanceProfileName",
                                              inst_pro["InstanceProfileName"])
            if aws_inst_pro is None:
                self.iw.create_instance_profile(inst_pro["InstanceProfileName"], inst_pro["Path"])
                self.iw.add_role_to_instance_profile(mem_role["RoleName"], inst_pro["InstanceProfileName"])
            else:
                if inst_pro["Path"] != aws_inst_pro["Path"]:
                    print("WARNING Paths differ for Instance Profile {}: Path_In_File={} Path_In_AWS={}".format(
                        inst_pro["InstanceProfileName"], inst_pro["Path"], aws_inst_pro["Path"]))
                    print("You will need to manually delete the old instance profile for the Path to be changed.")
        for aws_ip in aws_role["InstanceProfileList"]:
            mem_ip = utils.find_dict_with(mem_role["InstanceProfileList"], "InstanceProfileName", aws_ip["InstanceProfileName"])
            if mem_ip is None:
                # AWS has an instance profile that is not in memory version, it should be deleted.
                self.iw.remove_role_from_instance_profile(mem_role["RoleName"], aws_ip["InstanceProfileName"])
                self.iw.delete_instance_profile(aws_ip["InstanceProfileName"])

    def save_roles(self, filename):
        with open(filename, 'w') as f:
            json.dump(self.roles, f, indent=2, sort_keys=True)

    def load_roles_from_file(self, filename):
        with open(filename, 'r') as f:
            self.roles = json.load(f)

    def extract_groups_from_iam_details(self):
        group_temp_list = []
        for group in self.iam_details["GroupDetailList"]:
            if self.filter("GroupName", self.group_keyword_filters, self.group_whole_filters, group):
                print("filtering: " + group["GroupName"])
                continue

            new_group = {'GroupName': group['GroupName'],
                        'Path': group['Path']}

            managed_pol_list = []
            for mp_pol in group["AttachedManagedPolicies"]:
                managed_pol_list.append(mp_pol["PolicyArn"])
            new_group["AttachedManagedPolicies"] = managed_pol_list

            inst_pol_group_list = []
            for inst_pol in group["GroupPolicyList"]:
                doc = {}
                doc["PolicyDocument"] = inst_pol["PolicyDocument"]
                doc["PolicyName"] = inst_pol["PolicyName"]
                inst_pol_group_list.append(inst_pol)
            new_group["GroupPolicyList"] = inst_pol_group_list

            group_temp_list.append(new_group)
        self.groups = self.to_prod_account(group_temp_list)

    def create_full_group(self, group):
        self.iw.create_group(group["GroupName"], group["Path"])
        for inline_pol in group["GroupPolicyList"]:
            self.iw.put_group_policy(group["GroupName"], inline_pol["PolicyName"], inline_pol["PolicyDocument"])
        for mngd_pol_arn in group["AttachedManagedPolicies"]:
            self.iw.attach_group_policy(group["GroupName"], mngd_pol_arn)

    def adjust_groups_in_aws(self, use_assume_role=False):
        '''
        Adjusts the AWS groups to match the current in memory groups. It creates the groups if
        they do not exist in AWS.  Also adjusts attached managed policies and inline policies associated with the group
         It will not delete any groups.
        Args:
            use_assume_role: set to True if using developer account credentials and plan to assume production credentials

        Returns:

        '''
        if use_assume_role:
            import_session = assume_production_role(self.session)
        else:
            import_session = self.session
        if self.iam_details == None:
            print("iam_details must be imported first.")
            return
        for group in self.groups:
            client = import_session.client('iam')
            aws_group = utils.find_dict_with(self.iam_details["GroupDetailList"], "GroupName",  group["GroupName"])
            if aws_group is None:
                self.create_full_group(group)
            else:
                self.validate_group(client, group, aws_group)

    def validate_group(self, client, mem_group, aws_group):
        if mem_group["GroupName"] != aws_group["GroupName"]:
            print("Cannot validate different Groups: {} and {}".format(mem_group["GroupName"], aws_group["GroupName"]))
            return
        if mem_group["Path"] != aws_group["Path"]:
            print("WARNING Paths differ for group {}: Path_In_File={} Path_In_AWS={}".format(mem_group["GroupName"],
                                                                                             mem_group["Path"],
                                                                                             aws_group["Path"]))
            print("You will need to manually delete the old group for the Path to be changed.")

        for inline_pol in mem_group["GroupPolicyList"]:
            aws_inline_pol = utils.find_dict_with(aws_group["GroupPolicyList"], "PolicyName", inline_pol["PolicyName"])
            if aws_inline_pol is None:
                self.iw.put_group_policy(mem_group["GroupName"], inline_pol["PolicyName"], inline_pol["PolicyDocument"])
                continue
            aws_doc_str = json.dumps(aws_inline_pol["PolicyDocument"], indent=2, sort_keys=True)
            mem_doc_str = json.dumps(inline_pol["PolicyDocument"], indent=2, sort_keys=True)
            if mem_doc_str != aws_doc_str:
                self.iw.put_group_policy(mem_group["GroupName"], inline_pol["PolicyName"], inline_pol["PolicyDocument"])
        for aws_inline_pol in aws_group["GroupPolicyList"]:
            matching_mem_pol = utils.find_dict_with(mem_group["GroupPolicyList"], "PolicyName", aws_inline_pol["PolicyName"])
            if matching_mem_pol is None:
                # AWS has a policy that is not in memory version, it should be deleted.
                self.iw.delete_group_policy(mem_group["GroupName"], aws_inline_pol["PolicyName"])

        for mngd_pol_arn in mem_group["AttachedManagedPolicies"]:
            self.iw.attach_group_policy(mem_group["GroupName"], mngd_pol_arn)
        for aws_mngd_pol in aws_group["AttachedManagedPolicies"]:
            if aws_mngd_pol["PolicyArn"] not in mem_group["AttachedManagedPolicies"]:
                # AWS has a mngd policy that is not in memory version, it should be deleted.
                self.iw.detach_group_policy(mem_group["GroupName"], aws_mngd_pol["PolicyArn"])

    def save_groups(self, filename):
        with open(filename, 'w') as f:
            json.dump(self.groups, f, indent=2, sort_keys=True)

    def load_groups_from_file(self, filename):
        with open(filename, 'r') as f:
            self.groups = json.load(f)

    def print_alarms(self, filename=None):
        client = self.session.client("cloudwatch")
        response = client.describe_alarms(
            MaxRecords=100
        )
        pprint.pprint(response)

    def export_from_aws_to_files(self):
        self.get_iam_details_from_aws()

        self.extract_policies_from_iam_details()
        self.save_policies(DEFAULT_POLICY_FILE)

        self.extract_roles_from_iam_details()
        self.save_roles(DEFAULT_ROLES_FILE)

        self.extract_groups_from_iam_details()
        self.save_groups(DEFAULT_GROUP_FILE)

    def change_account_memory(self):
        self.policies = self.to_sessions_account(self.policies)
        self.roles = self.to_sessions_account(self.roles)
        self.groups = self.to_sessions_account(self.groups)

    def load_from_files(self):
        self.load_policies_from_file(DEFAULT_POLICY_FILE)
        self.load_roles_from_file(DEFAULT_ROLES_FILE)
        self.load_groups_from_file(DEFAULT_GROUP_FILE)

    def import_to_aws(self, use_assume_role=False):
        if self.iam_details is None:
            self.get_iam_details_from_aws()
        self.change_account_memory()
        self.adjust_policies_in_aws()
        self.adjust_roles_in_aws()
        self.adjust_groups_in_aws()

    def delete_policies(self,  use_assume_role=False):
        if use_assume_role:
            import_session = assume_production_role(self.session)
        else:
            import_session = self.session
        acc = aws.get_account_id_from_session(import_session)
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



def get_oldest_policy_version(policy):
    versions = []
    for ver in policy["PolicyVersionList"]:
        versions.append(int(ver["VersionId"][1:]))
    versions.sort()
    print(str(versions))
    return "v" + str(versions[0])


def get_default_policy_version(policy):
    return utils.find_dict_with(policy["PolicyVersionList"], "VersionId", policy["DefaultVersionId"])


if __name__ == '__main__':
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    parser = argparse.ArgumentParser(description="Load Policies, Roles and Groups into and out of AWS",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog='Exports and Imports Iam Information')
    parser.add_argument("--aws-credentials", "-a",
                        metavar="<file>",
                        default=os.environ.get("AWS_CREDENTIALS"),
                        type=argparse.FileType('r'),
                        help="File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")

    parser.add_argument("command",
                        choices=COMMANDS,
                        help="import from files to AWS, export from AWS to files. Files will be manaually edited so export should not be used after initial file creation.")

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    session = aws.create_session(args.aws_credentials)
    iam = IamUtils(session)

    if args.command == "export":
        print("Exporting from AWS...")
        iam.export_from_aws_to_files()
    elif args.command == "import":
        print("Importing to AWS...")
        iam.load_from_files()
        iam.import_to_aws()
    else:
        print("Uknown Command.")






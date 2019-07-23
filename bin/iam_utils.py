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

names.json
{
    "roles": [],
    "groups": [],
    "policies": [],
}
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
from lib import constants as const
from lib.boto_wrapper import IamWrapper
from lib import configuration
from lib import console

REGION_STANDIN = '==region=='
ACCOUNT_STANDIN = '==account=='

IAM_CONFIG_DIR = const.repo_path("config", "iam")
DEFAULT_POLICY_FILE = os.path.join(IAM_CONFIG_DIR, "policies.json")
DEFAULT_GROUP_FILE = os.path.join(IAM_CONFIG_DIR, "groups.json")
DEFAULT_ROLES_FILE = os.path.join(IAM_CONFIG_DIR, "roles.json")
DEFAULT_NAMES_FILE = os.path.join(IAM_CONFIG_DIR, "names.json")

class AllResources(object):
    """Class that always returns True for any `obj in AllResources()`"""
    def __contains__(self, value):
        return True

def json_dumps(obj):
    """A wrapper to `json.dumps` that provides the common arguments used
    throughout the code

    Args:
        obj (object): Object to convert to JSON

    Returns:
        str: String containing formatted JSON
    """
    return json.dumps(obj, indent=2, sort_keys=True)

def pformat_truncate(o, width=50):
    """Convert the object to printable representation and truncate it if too long

    Note: If the object is a multiline string or pformat returns a multiline
          string, only the first line of the string will be returned

    Args:
        o (object): Object to be displayed
        width (int): Maximum length for the resulting string

    Returns:
        str: String containing the formatted object
    """
    s = pprint.pformat(o)
    split = '\n' in s
    if split:
        s = s.splitlines()[0]
    if len(s) > width:
        s = s[:width-3] + '...'
    elif split:
        # If the line wasn't truncated but was the first line
        # in a multi-line string then add a marker so we know
        # that the result was modified
        s = s + '...'
    return s

class DryRunWrapper(object):
    """Wrapper around a Boto3 IAM client object that will print calls to specific
    functions instead of executing them. If the requested function is not on the
    blacklist then it will be allowed to execute
    """

    def __init__(self, to_wrap):
        """Args:
            to_wrap (Client): Boto3 IAM Client to wrap
        """
        self.to_wrap = to_wrap
        self.prefix = 'boto3.client("iam").'
        self.functions = [
            # Groups
            'create_group',
            'put_group_policy',
            'attach_group_policy',
            'delete_group_policy',
            'detach_group_policy',
            'add_role_to_instance_profile',
            'create_instance_profile',
            'remove_role_from_instance_profile',
            'delete_instance_profile',

            # Roles
            'create_role',
            'update_assume_role_policy',
            'put_role_policy',
            'attach_role_policy',
            'delete_role_policy',
            'detach_role_policy',

            # Policies
            'create_policy',
            'delete_policy_version',
            'create_policy_version',
        ]
        # ???: Redirect any function starting with create/put/attach/delete/detach/add/remove/update

    def __getattr__(self, function):
        if function not in self.functions:
            return getattr(self.to_wrap, function)

        def call(*args, **kwargs):
            """Standin for the requested function that will print the function and arguments"""
            args_kwargs = ", ".join([*[pformat_truncate(arg) for arg in args],
                                     *["{} = {}".format(k, pformat_truncate(v))
                                       for k, v in kwargs.items()]])
            console.debug("{}{}({})".format(self.prefix, function, args_kwargs))

        return call

class IamUtils(object):
    """Object for exporting or importing IAM groups, roles, and policies"""

    def __init__(self, bosslet_config, dry_run=False):
        """
        Args:
            bosslet_config (BossConfiguration): Bosslet to export from or import to
        """
        self.bosslet_config = bosslet_config
        self.session = bosslet_config.session
        self.client = self.session.client('iam')
        if dry_run:
            self.client = DryRunWrapper(self.client)
        self.iw = IamWrapper(self.client)

    ######################################################
    ## Generic functions the are resource type agnostic ##
    ######################################################

    def to_generic(self, data):
        """Replace region and account references with standin values"""
        # str(ACCOUNT_ID) used as the value could be an integer
        data = data.replace(self.bosslet_config.REGION, REGION_STANDIN)
        data = data.replace(str(self.bosslet_config.ACCOUNT_ID), ACCOUNT_STANDIN)
        return data

    def from_generic(self, data):
        """Replace standin values with the bosslet's region and account reference"""
        # str(ACCOUNT_ID) used as the value could be an integer
        data = data.replace(REGION_STANDIN, self.bosslet_config.REGION)
        data = data.replace(ACCOUNT_STANDIN, str(self.bosslet_config.ACCOUNT_ID))
        return data

    def export(self, resource_type, filename, filters=[]):
        """Export the requested groups/roles/policies from IAM and save to the given file

        Args:
            resource_type (str): One of - groups, roles, policies
            filename (str): Name of the file to save the results to
            filters (list[str]): List of group/role/policy names that should be exported
        """
        objects = self.load_from_aws(resource_type, filters)
        self.save(filename, objects)

    def save(self, filename, objects):
        """Save the given IAM objects to disk

        Note: serialized objects will have bosslet specific values removed

        Args:
            filename (str): Name of the file to save the results to
            objects (object): Objects to be serialized, converted, and saved
        """
        with open(filename, 'w') as fh:
            data = json_dumps(objects)
            data = self.to_generic(data) # Replace stack specific values
            fh.write(data)

    def load(self, resource_type, filename, filters=[]):
        """Load previously exported data from disk

        Note: Loaded data is compaired against the filter list and any filtered
              out items will produce a warning message

        Args:
            resource_type (str): One of - groups, roles, policies
            filename (str): Name of the file with data to load
            filters (list[str]): List of group/role/policy names that should be loaded

        Returns:
            list[objects]: List of filtered objects
        """
        with open(filename, 'r') as fh:
            data = fh.read()
            data = self.from_generic(data) # Replace generic values
            data = json.loads(data)

        key = {
            'groups': 'GroupName',
            'roles': 'RoleName',
            'policies': 'PolicyName',
        }[resource_type]

        # Verify that the loaded data is valid
        objects = []
        for item in data:
            if item[key] not in filters:
                fmt = "{} {} not in whitelist, not importing"
                console.warning(fmt.format(resource_type, item[key]))
            else:
                objects.append(item)

        return objects

    def load_from_aws(self, resource_type, names=[]):
        """Load the current IAM resources

        The IAM results are convereted to the internal representation used and
        filtered to only include the requested resources

        Args:
            resource_type (str): One of - groups, roles, policies
            names (list[str]): List of group/role/policy names that should be loaded

        Returns:
            list[objects]: List of converted and filtered objects
        """
        if resource_type == 'groups':
            filter = ['Group']
            list_key = 'GroupDetailList'
            name_key = 'GroupName'
        elif resource_type == 'roles':
            filter = ['Role']
            list_key = 'RoleDetailList'
            name_key ='RoleName'
        elif resource_type == 'policies':
            filter = ['LocalManagedPolicy']
            list_key = 'Policies'
            name_key ='PolicyName'
        else:
            raise ValueError("resource_type '{}' is not supported".format(resource_type))

        resources = []

        kwargs = { 'MaxItems': 1000, 'Filter': filter }
        resp = {'IsTruncated': True}
        while resp['IsTruncated']:
            resp = self.client.get_account_authorization_details(**kwargs)
            kwargs['Marker'] = resp.get('Marker')

            resources.extend([self.extract(resource_type, item)
                              for item in resp[list_key]
                              if item[name_key] in names])

        return resources

    def extract(self, resource_type, resource):
        """Convert the IAM object into the internal representation used

        Args:
            resource_type (str): One of - groups, roles, policies
            resource (object): IAM object

        Returns:
            object: Converted IAM object
        """
        if resource_type == 'groups':
            group = {
                'GroupName': resource['GroupName'],
                'Path': resource['Path'],
                'AttachedManagedPolicies': [policy['PolicyArn']
                                           for policy in resource['AttachedManagedPolicies']],
                'GroupPolicyList': [{'PolicyDocument': policy['PolicyDocument'],
                                     'PolicyName': policy['PolicyName']}
                                    for policy in resource['GroupPolicyList']],
            }
            return group
        elif resource_type == 'roles':
            role = {
                'RoleName': resource['RoleName'],
                'Path': resource['Path'],
                'AssumeRolePolicyDocument': resource['AssumeRolePolicyDocument'],
                'AttachedManagedPolicies': [policy['PolicyArn']
                                           for policy in resource['AttachedManagedPolicies']],
                'RolePolicyList': resource['RolePolicyList'],
                'InstanceProfileList': [{'InstanceProfileName': profile['InstanceProfileName'],
                                         'Path': profile['Path']}
                                        for profile in resource['InstanceProfileList']],
            }
            return role
        elif resource_type == 'policies':
            for version in resource['PolicyVersionList']:
                if version['IsDefaultVersion']:
                    policy = {
                        'PolicyName': resource['PolicyName'],
                        'Path': resource['Path'],
                        'PolicyDocument': version['Document'],
                    }
                    if 'Description' in resource:
                        policy['Description'] = policy['Description']
                    return policy

    def import_(self, resource_type, filename, filters=[]):
        """Load the given groups/roles/policies and import them into IAM

        Args:
            resource_type (str): One of - groups, roles, policies
            filename (str): Name of the file containing exported data to load
            filters (list[str]): List of group/role/policy names that should be imported
        """
        current = self.load_from_aws(resource_type, filters)
        desired = self.load(resource_type, filename, filters)
        self.update_aws(resource_type, current, desired)

    def update_aws(self, resource_type, current, desired):
        """Compare loaded data against the current data in IAM and create or
        update IAM to reflect the loaded data

        Args:
            resource_type (str): One of - groups, roles, policies
            current (list[object]): List of objects loaded from IAM
            desired (list[object]): Lost of objects loaded from disk
        """
        key = {
            'groups': 'GroupName',
            'roles': 'RoleName',
            'policies': 'PolicyName',
        }[resource_type]

        lookup = { resource[key]: resource
                   for resource in current }

        for resource in desired:
            resource_ = lookup.get(resource[key])
            if resource_ is None: # Doesn't exist currently, create
                console.info("Creating {} {}".format(key[:-4], resource[key]))

                try:
                    if resource_type == 'groups':
                        self.group_create(resource)
                    elif resource_type == 'roles':
                        self.role_create(resource)
                    elif resource_type == 'policies':
                        self.policy_create(resource)
                except ClientError as ex:
                    if ex.response['Error']['Code'] == 'EntityAlreadyExists':
                        console.error("{} {} already exists cannot load again.".format(key, resource[key]))
                    else:
                        console.error("Problem creating {}: {}".format(resource_type, resource[key]))
                        console.error("\tDetails: {}".format(str(ex)))
            else: # Currently exists, compare and update
                console.info("Updating {} {}".format(key[:-4], resource[key]))

                if resource['Path'] != resource_['Path']:
                    console.warning("Paths differ for {} {}: '{}' != '{}'".format(key,
                                                                                  resource[key],
                                                                                  resource['Path'],
                                                                                  resource_['Path']))
                    console.info("You will need to manually delete the old resource for the Path to be changed")
                    continue

                if resource_type == 'groups':
                    self.group_update(resource, resource_)
                elif resource_type == 'roles':
                    self.role_update(resource, resource_)
                elif resource_type == 'policies':
                    self.policy_update(resource, resource_)

    ######################################################
    ## Resource type specific create / update functions ##
    ######################################################

    ##########
    # Groups

    def group_create(self, resource):
        """Create a new IAM Group

        Args:
            resource (object): IAM Group definition to create
        """
        self.iw.create_group(resource["GroupName"], resource["Path"])

        for policy in resource["GroupPolicyList"]:
            self.iw.put_group_policy(resource["GroupName"],
                                     policy["PolicyName"],
                                     policy["PolicyDocument"])

        for policy in resource["AttachedManagedPolicies"]:
            self.iw.attach_group_policy(resource["GroupName"], policy)

    def group_update(self, resource, resource_):
        """Compare and potentially update the referenced IAM Group

        Args:
            resource (object): Desired IAM Group definition
            resource_ (object): Current IAM Group definition
        """
        lookup = { policy['PolicyName'] : policy['PolicyDocument']
                   for policy in resource_['GroupPolicyList'] }
        for policy in resource["GroupPolicyList"]:
            policy_ = lookup.get(policy['PolicyName'])
            if policy_ is None:
                self.iw.put_group_policy(resource["GroupName"],
                                         policy["PolicyName"],
                                         policy["PolicyDocument"])
            else:
                del lookup[policy['PolicyName']]
                document = json_dumps(policy['PolicyDocument'])
                document_ = json_dumps(policy_)
                if document != document_:
                    self.iw.put_group_policy(resource["GroupName"],
                                             policy["PolicyName"],
                                             policy["PolicyDocument"])

        for policy in lookup.keys():
            # AWS has a policy that is not in the desired version, it should be deleted.
            self.iw.delete_group_policy(resource['GroupName'], policy)

        for arn in resource["AttachedManagedPolicies"]:
            if arn not in resource_['AttachedManagedPolicies']:
                self.iw.attach_group_policy(resource["GroupName"], arn)

        for arn in resource_['AttachedManagedPolicies']:
            if arn not in resource['AttachedManagedPolicies']:
                # AWS has a managed policy that is not in the desired version, it should be deleted.
                self.iw.detach_group_policy(resource["GroupName"], arn)

    #########
    # Roles

    def role_create(self, resource):
        """Create a new IAM Role

        Args:
            resource (object): IAM Role definition to create
        """
        self.iw.create_role(resource['RoleName'],
                            resource['Path'],
                            json_dumps(resource['AssumeRolePolicyDocument']))

        for policy in resource['RolePolicyList']:
            self.iw.put_role_policy(resource['RoleName'],
                                    policy['PolicyName'],
                                    policy['PolicyDocument'])

        for policy in resource['AttachedManagedPolicies']:
            self.iw.attach_role_policy(resource['RoleName'],
                                       policy)

        for profile in resource['InstanceProfileList']:
            self.iw.create_instance_profile(profile['InstanceProfileName'],
                                            profile['Path'])
            self.iw.add_role_to_instance_profile(resource['RoleName'],
                                                 profile['InstanceProfileName'])

    def role_update(self, resource, resource_):
        """Compare and potentially update the referenced IAM Role

        Args:
            resource (object): Desired IAM Role definition
            resource_ (object): Current IAM Role definition
        """
        policy = json_dumps(resource['AssumeRolePolicyDocument'])
        policy_ = json_dumps(resource_['AssumeRolePolicyDocument'])
        if policy != policy_:
            console.warning('Role policy document differs')
            self.iw.update_assume_role_policy(resource['RoleName'],
                                              resource['AssumeRolePolicyDocument'])

        lookup = { policy['PolicyName']: policy['PolicyDocument']
                   for policy in resource_['RolePolicyList'] }
        for policy in resource['RolePolicyList']:
            policy_ = lookup.get(policy['PolicyName'])
            if policy_ is None:
                self.iw.put_role_policy(resource['RoleName'],
                                        policy['PolicyName'],
                                        policy['PolicyDocument'])
            else:
                document = json_dumps(policy['PolicyDocument'])
                document_ = json_dumps(policy_)
                if document != document_:
                    self.iw.put_role_policy(resource['RoleName'],
                                            policy['PolicyName'],
                                            policy['PolicyDocument'])

        for policy in lookup.keys():
            # AWS has a policy that is not in the desired version, it should be deleted
            self.iw.delete_role_policy(resource['RoleName'], policy)

        for arn in resource['AttachedManagedPolicies']:
            if arn not in resource_['AttachedManagedPolicies']:
                self.iw.attach_role_policy(resource["RoleName"], arn)

        for arn in resource_['AttachedManagedPolicies']:
            if arn not in resource['AttachedManagedPolicies']:
                # AWS has a managed policy that is not in the desired version, it should be deleted.
                self.iw.detach_role_policy(resource["RoleName"], arn)

        lookup = { profile['InstanceProfileName']: profile
                   for profile in resource_['InstanceProfileList'] }
        for profile in resource['InstanceProfileList']:
            profile_ = lookup.get(profile['InstanceProfileName'])
            if policy_ is None:
                self.iw.create_instance_profile(profile['InstanceProfileName'],
                                                profile['Path'])
                self.iw.add_role_to_instance_profile(role['RoleName'],
                                                     profile['InstanceProfileName'])
            else:
                if profile['Path'] != profile_['Path']:
                    console.warning("Paths differ for {} Instance Profile {}: '{}' != '{}'".format(resource['RoleName'],
                                                                                                   profile['InstanceProfileName'],
                                                                                                   profile['Path'],
                                                                                                   profile_['Path']))
                    console.info('You will need to manually delete the old instance profile for the Path to be changed')

        for profile in lookup.keys():
            # AWS has an instance profile that is not in the desired version, it should be deleted
            self.iw.remove_role_from_instance_profile(resource['RoleName'], profile)
            self.iw.delete_instance_profile(profile)

    ############
    # Policies

    def policy_create(self, resource):
        """Create a new IAM Policy

        Args:
            resource (object): IAM Policy definition to create
        """
        resource['PolicyDocument'] = json_dumps(resource['PolicyDocument'])
        self.client.create_policy(**resource)

    def policy_arn(self, resource):
        """Build the Policies ARN from its definition"""
        return "arn:aws:iam::{}:policy{}{}".format(self.bosslet_config.ACCOUNT_ID,
                                                   resource['Path'],
                                                   resource['PolicyName'])

    def delete_oldest_policy_version(self, policy_name, arn):
        """Query for the current policy versions and delete the oldest one if
        there are 5 versions (the maximum number allowed)
        """
        resp = self.client.list_policy_versions(PolicyArn = arn)
        if len(resp['Versions']) == 5:
            versions = [int(version['VersionId'][1:]) for version in resp['Versions']]
            versions.sort()
            resp = self.client.delete_policy_version(PolicyArn = arn,
                                                     VersionId = 'v' + str(versions[0]))

    def policy_update(self, resource, resource_):
        """Compare and potentially update the referenced IAM Policy

        Args:
            resource (object): Desired IAM Policy definition
            resource_ (object): Current IAM Policy definition
        """
        policy = json_dumps(resource['PolicyDocument'])
        policy_ = json_dumps(resource['PolicyDocument'])
        if policy != policy_:
            console.warning("Default policy differs")

            arn = self.policy_arn(resource)
            self.delete_oldest_policy_version(resource['PolicyName'], arn)

            self.client.create_policy_version(PolicyArn = arn,
                                              PolicyDocument = resource['PolicyDocument'],
                                              SetAsDefault = True)

if __name__ == '__main__':
    parser = configuration.BossParser(description="Load Policies, Roles and Groups into and out of AWS",
                                      formatter_class=argparse.RawDescriptionHelpFormatter,
                                      epilog='Exports and Imports Iam Information')
    parser.add_argument('--names', '-n',
                        default=DEFAULT_NAMES_FILE,
                        help='JSON document containing the whitelist of names that should be exported/imported')
    parser.add_argument('--groups', '-g',
                        default=DEFAULT_GROUP_FILE,
                        help='JSON document where exported data is saved to or data to import is read from')
    parser.add_argument('--roles', '-r',
                        default=DEFAULT_ROLES_FILE,
                        help='JSON document where exported data is saved to or data to import is read from')
    parser.add_argument('--policies', '-p',
                        default=DEFAULT_POLICY_FILE,
                        help='JSON document where exported data is saved to or data to import is read from')
    parser.add_argument('--dry-run', '-d',
                        action='store_true',
                        help='If the import should be dry runned')
    parser.add_bosslet()
    parser.add_argument("command",
                        choices = ['export', 'import'])
    parser.add_argument("resource_type",
                        choices = ['groups', 'roles', 'policies'],
                        nargs='+')

    args = parser.parse_args()

    with open(args.names, 'r') as fh:
        filters = json.load(fh)

    iam = IamUtils(args.bosslet_config, args.dry_run)
    if args.command == 'import':
        for resource_type in args.resource_type:
            iam.import_(resource_type, getattr(args, resource_type), filters[resource_type])
    else: # export
        for resource_type in args.resource_type:
            iam.export(resource_type, getattr(args, resource_type), filters[resource_type])


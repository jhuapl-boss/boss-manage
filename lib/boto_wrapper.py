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
Wrapper class to wrap boto calls to catch errors and make it easier to read code.

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

class IamWrapper:

    def __init__(self, client):
        """
        Initializes the class.
        Args:
            client: boto3 iam client
        """
        self.client = client

    def create_group(self, group_name, path):
        try:
            self.client.create_group(GroupName=group_name, Path=path)
        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityAlreadyExists':
                print("WARNING Group {} already exists, it cannot be loaded again.".format(group_name))
            else:
                print("ERROR occured creating group: {}".format(group_name))
                print("   Details: {}".format(str(e)))

    def put_group_policy(self, group_name, policy_name, policy_document):
        pol_doc_str = json.dumps(policy_document, indent=2, sort_keys=True)
        try:
            self.client.put_group_policy(GroupName=group_name, PolicyName=policy_name, PolicyDocument=pol_doc_str)
        except ClientError as e:
                print("ERROR occured creating group {}'s inline policy: {}".format(group_name, policy_name))
                print("   Details: {}".format(str(e)))

    def attach_group_policy(self, group_name, policy_arn):
        try:
            self.client.attach_group_policy(GroupName=group_name, PolicyArn=policy_arn)
        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityAlreadyExists':
                print("WARNING Group {} already contains managed policy: {}".format(group_name, policy_arn))
            else:
                print("ERROR occured creating group: {}".format(group_name))
                print("   Details: {}".format(str(e)))

    def delete_group_policy(self, group_name, policy_name):
        try:
            self.client.delete_group_policy(GroupName=group_name, PolicyName=policy_name)
        except ClientError as e:
                print("ERROR occured deleting group {}'s inline policy: {}".format(group_name, policy_name))
                print("   Details: {}".format(str(e)))

    def detach_group_policy(self, group_name, policy_arn):
        try:
            self.client.detach_group_policy(GroupName=group_name, PolicyArn=policy_arn)
        except ClientError as e:
            print("ERROR occured detaching policy, {}, from group {}".format(policy_arn, group_name))
            print("   Details: {}".format(str(e)))

    def add_role_to_instance_profile(self, role_name, instance_profile_name):
        try:
            self.client.add_role_to_instance_profile(RoleName=role_name, InstanceProfileName=instance_profile_name)
        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityAlreadyExists':
                print("WARNING Instance Profile {} already contains Role: {}".format(instance_profile_name, role_name))
            else:
                print("ERROR occured adding role, {}, to instance profile: {}".format(role_name, instance_profile_name))
                print("   Details: {}".format(str(e)))

    def create_instance_profile(self, instance_profile_name, path):
        try:
            self.client.create_instance_profile(InstanceProfileName=instance_profile_name, Path=path)
        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityAlreadyExists':
                print("WARNING Instance Profile {} already exists: {}".format(instance_profile_name))
            else:
                print("ERROR occured creating instance profile: {}".format(instance_profile_name))
                print("   Details: {}".format(str(e)))

    def remove_role_from_instance_profile(self, role_name, instance_profile_name):
            try:
                self.client.remove_role_from_instance_profile(RoleName=role_name, InstanceProfileName=instance_profile_name)
            except ClientError as e:
                print("ERROR occured adding role, {}, to instance profile: {}".format(role_name,
                                                                                      instance_profile_name))
                print("   Details: {}".format(str(e)))

    def delete_instance_profile(self, instance_profile_name):
            try:
                self.client.delete_instance_profile(InstanceProfileName=instance_profile_name)
            except ClientError as e:
                print("ERROR occured deleting instance profile: {}".format(instance_profile_name))
                print("   Details: {}".format(str(e)))

    def create_role(self, role_name, path, assume_role_policy_document):
        try:
            self.client.create_role(RoleName=role_name, Path=path, AssumeRolePolicyDocument=assume_role_policy_document)
        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityAlreadyExists':
                print("WARNING Role {} already exists, it cannot be loaded again.".format(role_name))
            else:
                print("ERROR occured creating role: {}".format(role_name))
                print("   Details: {}".format(str(e)))

    def update_assume_role_policy(self, role_name, policy_document):
        pol_doc_str = json.dumps(policy_document, indent=2, sort_keys=True)
        try:
            self.client.update_assume_role_policy(RoleName=role_name, PolicyDocument=pol_doc_str)
        except ClientError as e:
            print("ERROR occured updating role {}'s assume role policy document: ".format(role_name))
            pprint.pprint(policy_document)
            print("   Details: {}".format(str(e)))


    def put_role_policy(self, role_name, policy_name, policy_document):
        pol_doc_str = json.dumps(policy_document, indent=2, sort_keys=True)
        try:
            self.client.put_role_policy(RoleName=role_name, PolicyName=policy_name, PolicyDocument=pol_doc_str)
        except ClientError as e:
            print("ERROR occured creating role {}'s inline policy: {}".format(role_name, policy_name))
            print("   Details: {}".format(str(e)))


    def attach_role_policy(self, role_name, policy_arn):
        try:
            self.client.attach_role_policy(RoleName=role_name, PolicyArn=policy_arn)
        except ClientError as e:
            if e.response['Error']['Code'] == 'EntityAlreadyExists':
                print("WARNING Role {} already contains managed policy: {}".format(role_name, policy_arn))
            else:
                print("ERROR occured creating role: {}".format(role_name))
                print("   Details: {}".format(str(e)))


    def delete_role_policy(self, role_name, policy_name):
        try:
            self.client.delete_role_policy(RoleName=role_name, PolicyName=policy_name)
        except ClientError as e:
            print("ERROR occured deleting role {}'s inline policy: {}".format(role_name, policy_name))
            print("   Details: {}".format(str(e)))


    def detach_role_policy(self, role_name, policy_arn):
        try:
            self.client.detach_role_policy(RoleName=role_name, PolicyArn=policy_arn)
        except ClientError as e:
            print("ERROR occured detaching policy, {}, from role {}".format(policy_arn, role_name))
            print("   Details: {}".format(str(e)))


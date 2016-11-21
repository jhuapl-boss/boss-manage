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
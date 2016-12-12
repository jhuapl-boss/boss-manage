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

import os
import subprocess
import sys
import unittest

import alter_path
from scalyr import *


class TestScalyr(unittest.TestCase):
    def test_create_monitors_if_not_found(self):
        jsonObj = {}
        actual = get_cloudwatch_obj(jsonObj, 'us-east-1')
        expected = {
            'type': 'cloudwatch',
            'region': 'us-east-1',
            'accessKey': '',
            'secretKey': '',
            'executionIntervalMinutes': 5,
            'metrics': []
        }

        self.assertEqual(expected, actual)

        expectedJsonObj = {
            'monitors': [
                {
                    'type': 'cloudwatch',
                    'region': 'us-east-1',
                    'accessKey': '',
                    'secretKey': '',
                    'executionIntervalMinutes': 5,
                    'metrics': []
                }
            ]
        }

        self.assertEqual(expectedJsonObj, jsonObj)

    def test_create_cloudwatch_if_monitors_empty(self):
        jsonObj = { 'monitors': [] }
        actual = get_cloudwatch_obj(jsonObj, 'us-east-1')
        expected = {
            'type': 'cloudwatch',
            'region': 'us-east-1',
            'accessKey': '',
            'secretKey': '',
            'executionIntervalMinutes': 5,
            'metrics': []
        }

        self.assertEqual(expected, actual)

        expectedJsonObj = {
            'monitors': [
                {
                    'type': 'cloudwatch',
                    'region': 'us-east-1',
                    'accessKey': '',
                    'secretKey': '',
                    'executionIntervalMinutes': 5,
                    'metrics': []
                }
            ]
        }

        self.assertEqual(expectedJsonObj, jsonObj)

    def test_get_cloudwatch_obj(self):
        expected = {'type': 'cloudwatch', 'region': 'us-east-1'}
        jsonObj = { 'monitors': [
            {'type': 'not it'},
            {'type': 'cloudwatch', 'region': 'some other region'},
            copy(expected) ]
        }
        actual = get_cloudwatch_obj(jsonObj, 'us-east-1')
        self.assertEqual(expected, actual)

    def test_add_single_instance(self):
        instId = 'rockstar'
        expected = [{
            'namespace': 'AWS/EC2',
            'metric': 'StatusCheckFailed',
            'dimensions': { 'InstanceId': instId }
        }]
        metricsObj = []
        add_single_instance(metricsObj, instId)
        self.assertEqual(expected, metricsObj)

    def test_add_new_instances(self):
        instId1 = 'rockstar'
        instId2 = 'allstar'
        expected = [
            {
                'namespace': 'AWS/EC2',
                'metric': 'StatusCheckFailed',
                'dimensions': { 'InstanceId': instId1 }
            },
            {
                'namespace': 'AWS/EC2',
                'metric': 'StatusCheckFailed',
                'dimensions': { 'InstanceId': instId2 }
            }
        ]
        metrics = []
        add_new_instances(metrics, [instId1, instId2])
        self.assertEqual(expected, metrics)

    def test_download_config_file_raises_on_failure(self):
        with self.assertRaises(subprocess.CalledProcessError):
            # No Scalyr keys set, so should fail.
            download_config_file()

    def test_upload_config_file_raises_on_failure(self):
        with self.assertRaises(Exception):
            # Bad filename.
            upload_config_file('foo')

    def test_main_entry_point_returns_false_on_failure(self):
        # No Scalyr keys set, so should fail.
        self.assertFalse(add_instances_to_scalyr(None, 'foo', []) )

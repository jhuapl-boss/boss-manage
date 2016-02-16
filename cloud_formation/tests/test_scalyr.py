import os
import sys
import unittest

# Add a reference to parent so that we can import those files.
cur_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.normpath(os.path.join(cur_dir, ".."))
sys.path.append(parent_dir)
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

    def test_add_new_instance(self):
        instId = 'rockstar'
        expected = [{
            'namespace': 'AWS/EC2',
            'metric': 'StatusCheckFailed',
            'dimensions': { 'InstanceId': instId }
        }]
        metricsObj = []
        add_new_instance(metricsObj, instId)
        self.assertEqual(expected, metricsObj)

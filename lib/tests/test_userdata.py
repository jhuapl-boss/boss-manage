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

import unittest
import os, sys

# Allow unit test files to import the target library modules
cur_dir = os.path.dirname(os.path.realpath(__file__))
parent_dir = os.path.normpath(os.path.join(cur_dir, '..', '..'))
sys.path.append(parent_dir)

from lib.userdata import UserData


class TestUserData(unittest.TestCase):
    def test_format_for_cloudformation_1_section(self):
        cfg = """[aws]
        db = endpoint-db.theboss.io
        cache = cache.theboss.io
        """

        ud = UserData(None, cfg)
        ud['aws']['s3-flush-queue'] = '{"Ref": "S3FlushQueue"}'

        expected = [
            '\n[aws]\n', 
            'db = ', 'endpoint-db.theboss.io', '\n',
            'cache = ', 'cache.theboss.io', '\n',
            's3-flush-queue = ', {'Ref': 'S3FlushQueue'}, '\n'
        ]

        actual = ud.format_for_cloudformation()

        self.assertEqual(expected, actual)

    def test_format_for_cloudformation_multi_section(self):
        cfg = """[aws]
        db = endpoint-db.theboss.io
        cache = cache.theboss.io

        [vault]
        token = 12345abcde
        """

        ud = UserData(None, cfg)
        ud['aws']['s3-flush-queue'] = '{"Ref": "S3FlushQueue"}'

        expected = [
            '\n[aws]\n', 
            'db = ', 'endpoint-db.theboss.io', '\n',
            'cache = ', 'cache.theboss.io', '\n',
            's3-flush-queue = ', {"Ref": "S3FlushQueue"}, '\n',
            '\n[vault]\n',
            'token = ', '12345abcde', '\n'
        ]

        actual = ud.format_for_cloudformation()

        self.assertEqual(expected, actual)

    def test_format_for_cloudformation_with_default_section(self):
        """When there's a default section, its options are added to all
        non-default sections.
        """

        cfg = """[DEFAULT]
        global_option1 = foo
        global_option2 = bar

        [aws]
        db = endpoint-db.theboss.io
        cache = cache.theboss.io

        [vault]
        token = 12345abcde
        """

        ud = UserData(None, cfg)
        ud['aws']['s3-flush-queue'] = '{"Ref": "S3FlushQueue"}'

        expected = [
            '[DEFAULT]\n',
            'global_option1 = ', 'foo', '\n',
            'global_option2 = ', 'bar', '\n',
            '\n[aws]\n', 
            'global_option1 = ', 'foo', '\n',
            'global_option2 = ', 'bar', '\n',
            'db = ', 'endpoint-db.theboss.io', '\n',
            'cache = ', 'cache.theboss.io', '\n',
            's3-flush-queue = ', {'Ref': 'S3FlushQueue'}, '\n',
            '\n[vault]\n',
            'global_option1 = ', 'foo', '\n',
            'global_option2 = ', 'bar', '\n',
            'token = ', '12345abcde', '\n'
        ]

        actual = ud.format_for_cloudformation()

        self.assertEqual(expected, actual)


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

import json
import configparser
import io

class UserData:
    """A wrapper class around configparse.ConfigParser that automatically loads
    the default boss.config file and provide the ability to return the
    configuration file as a string. (ConfigParser can only write to a file
    object)

    When using CloudFormation template intrinsic functions such as Ref and
    Fn::GetAtt, use double quotes, not single quotes.  The strings are
    converted to dictionaries using the json library.  This library requires
    double quotes for key names and values that are strings.

    Ref and Fn:GetAtt let you use the logical name of the AWS resource.  When
    it is parsed by CloudFormation, the logical name will be replaced by a
    runtime value such as the resource's ARN, for example.
    """
    def __init__(self, config_file = "../salt_stack/salt/boss-tools/files/boss-tools.git/bossutils/boss.config.default", config_str = None):
        """Constructor.

        If config_file is None, tries to read user data from config_str,
        instead.  Currently does not allow providing both a file and a string.

        Args:
            config_file (string): Path to config file.
            config_str (string): User data as a string.
        """
        self.config = configparser.ConfigParser()
        self.config.optionxform = str  # this line perserves the case of the keys.
        if config_file is not None:
            self.config.read(config_file)
        elif config_str is not None:
            self.config.read_string(config_str)

    def __getitem__(self, key):
        return self.config[key]

    def __str__(self):
        buffer = io.StringIO()
        self.config.write(buffer)
        data = buffer.getvalue()
        buffer.close()
        return data

    def format_for_cloudformation(self):
        """Returns user data as a list of strings suitable for the Fn::Join statement.

        The returned list of strings is formatted so other intrinsic
        CloudFormation functions will be executed when parsed by
        CloudFormation.  This allows use of Ref and Fn::GetAtt which look up
        resources by logical name.

        Example return value:

        [
            '\n[aws]\n',
            'db = ', 'endpoint-db.theboss.io\n',
            'cache = ', 'cache.theboss.io\n',
            's3-flush-queue = ', {"Ref": "S3FlushQueue"}, '\n'
        ]

        Returns:
            (list): List of strings and dicts formatted for use with CloudFormation's Fn::Join function.
        """
        strs = []

        # The default section is treated specially if it exists.
        def_section = self.config.defaults()
        if len(def_section) > 0:
            strs.append('[' + self.config.default_section + ']\n')
        for (key, val) in def_section.items():
            strs.append(key + ' = ')
            strs.append(self._convert_str_to_dict(val))
            strs.append('\n')

        # Output the non-default sections.
        sections = self.config.sections()
        for sect in sections:
            strs.append('\n[' + sect + ']\n')
            for (key, val) in self.config.items(sect):
                strs.append(key + ' = ')
                strs.append(self._convert_str_to_dict(val))
                strs.append('\n')

        return strs

    def _convert_str_to_dict(self, str):
        """If string is a dictionary encoded as a string, create a dict.

        Uses json.loads() so keys and values must be enclosed with double
        quotes intead of single quotes.

        Args:
            str (string): Candidate string to possibly convert.

        Returns:
            (dict|string): Returns original string if not a dict.  Otherwise returns string converted to dict.
        """
        if str is None:
            return ''

        if type(str) == dict:
            return str

        stripped = str.strip()

        length = len(stripped)
        if length < 2:
            return str

        if stripped[0] != '{':
            return str

        if stripped[length-1] != '}':
            return str

        return json.loads(stripped)


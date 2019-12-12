#!/usr/bin/env python3

# Copyright 2019 The Johns Hopkins University Applied Physics Laboratory
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

import argparse
import textwrap

import alter_path
from lib import configuration

class ConfigCLI(configuration.BossCLI):
    def get_parser(self, ParentParser=configuration.BossParser):
        extended_help = textwrap.dedent("""Currently the following actions are supported:
        * No arguments: Verify and print the current bosslet configuration file, allowing a user
                        to see the final value of any computed values within the configuration file.
        * Expression: Evaluate the given expression that has access to the loaded bosslet configuration
                      object.
                      Example: --expression "bosslet.names.public_dns('api')" # to get the public hostname
                                                                              # of the bosslet's API server
        """)
        self.parser = ParentParser(description = 'Command for interacting with bosslet configuration files',
                                   formatter_class = argparse.RawDescriptionHelpFormatter,
                                   epilog = extended_help)
        self.parser.add_bosslet()
        self.parser.add_argument('--expression', '-e',
                                 metavar = '<expression>',
                                 help = 'Expression to evaluate (Variable `bosslet` is the loaded config)')
        return self.parser

    def run(self, args):
        if args.expression is None:
            args.bosslet_config.display()
        else:
            results = eval(args.expression, {'bosslet': args.bosslet_config})
            print(results)

if __name__ == '__main__':
    cli = ConfigCLI()
    cli.main()

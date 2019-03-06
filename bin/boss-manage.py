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

import importlib

import alter_path
from lib import configuration

def ref(module, cli):
    mod = importlib.import_module(module)
    return mod.__dict__[cli]

class ManageCLI(configuration.NestedBossCLI):
    COMMANDS = {
        'config': ref('boss-config', 'ConfigCLI'),
        'lambda': ref('boss-lambda', 'LambdaCLI'),
    }

    PARSER_ARGS = {
        'description': 'Command for creating or interacting with a Boss instance',
    }

    SUBPARSER_ARGS = {
        'dest': 'manage_method',
        'metavar': 'command',
        'help': 'boss-manage commands',
    }

if __name__ == '__main__':
    cli = ManageCLI()
    cli.main()

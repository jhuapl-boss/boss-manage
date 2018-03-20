# Copyright 2018 The Johns Hopkins University Applied Physics Laboratory
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

import sys
import json
import importlib

from . import constants as const
from . import aws

# DP TODO: Add caching

CONFIGS_JSON = "configs.json"
CONFIGS_PATH = const.repo_path("config", CONFIGS_JSON)

def load_configs():
    with open(CONFIGS_PATH, "r") as fh:
        try:
            return json.load(fh)
        except:
            print("ERROR: invalid json file '{}'".format(CONFIGS_PATH))
            return {}


def load_config(bosslet, cf_config = None):
    config = load_configs().get(bosslet)
    if config is None:
        return None

    if type(config) == type({}):
        # composed config

        if cf_config is None:
            raise ValueError("cf_config argument must not be None when using a composed boss_config")
        default = config.get('default')
        config = config.get(cf_config, default)
        if config is None:
            return None

    try:
        return importlib.import_module("config." + config)
    except ImportError:
        print("Could not import file 'config/{}'".format(config))
        return None

def valid_bosslet(bosslet):
    return load_configs().get(bosslet) is not None

class BossConfiguration(object):
    def __init__(self, bosslet, **kwargs):
        self.bosslet = bosslet

        self.ami_version = kwargs.get('ami_version')
        self.disable_preview = kwargs.get('disable_preview')

        self.aws_credentials = kwargs.get('aws_credentials')
        self.session = None
        if self.aws_credentials:
            # TODO: figure out how to handle sessions that are specific to a cf_config
            self.session = aws.create_session(self.aws_credentials, 'us-east-1')

    def __getitem__(self, cf_config):
        return load_config(self.bosslet, cf_config)

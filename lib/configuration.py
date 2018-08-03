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

import os
import sys
import json
import importlib
import warnings

from boto3.session import Session

from . import constants as const
from .external import ExternalCalls
from .ssh import SSHTarget
from .utils import keypair_to_file
from .names import AWSNames

# DP TODO: Add caching

# DP ???: Should the `cf_config` support be kept? It could be useful but also
#         complicates the code in this module a little bit. The external
#         interface wouldn't change
"""
DP NOTE: The references to `cf_config` are left from initial work to support
         multiple accounts. The current design is as follows:
         - The entry in configs.json would be a dictionary of bosslet config files
         - Each entry in resulting dictionary would be for a given CF config file
         - The `cf_config` variable would let the callee specify which CF config
           they need data for
         - The idea was/is that in a CF config it would be easy to reference
           resources from another CF config. In most cases the only thing needed
           would be the AWS or DNS name of the resource to reference, thus most
           of the heavy lifting would be done by AWSNames, but any value could be
           located.
           Example:
             In `api.py` to reference a subnet created in `core.py` the dev
             could use `bosslet_config['core'].names.subnet.external`

             In `api.py` to reference the public hostname of the Keycloak server
             from `auth.py` the dev could use `bosslet_config['auth'].names.public_dns('auth')`

         The `cf_config` variable was left in so that in the future there is a
         starting place for multi account support, if that is eventually added.
"""

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
        raise ValueError("multiple configuration setups not currently supported")

        if cf_config is None:
            raise ValueError("cf_config argument must not be None when using a composed boss_config")
        default = config.get('default')
        config = config.get(cf_config, default)
        if config is None:
            return None

    try:
        # Import the module / configuration file
        module = importlib.import_module("config." + config)

        # Create the session object
        if module.PROFILE:
            module.session = Session(profile_name = module.PROFILE,
                                     region_name = module.REGION)
        else:
            module.session = None

        # Load outbound bastion information in one location
        if module.OUTBOUND_BASTION:
            keyfile = keypair_to_file(module.OUTBOUND_KEY)
            if not os.path.exists(keyfile):
                raise ValueError("OUTBOUND_KEY '{}' doesn't exist".format(keyfile))
            module.outbound_bastion = SSHTarget(keyfile,
                                                module.OUTBOUND_IP,
                                                module.OUTBOUND_PORT,
                                                module.OUTBOUND_USER)
        else:
            module.outbound_bastion = None

        if module.SSH_KEY:
            keyfile = keypair_to_file(module.SSH_KEY)
            if not os.path.exists(keyfile):
                raise ValueError("SSH_KEY '{}' doesn't exist".format(keyfile))
            module.ssh_key = keyfile
        else:
            module.ssh_key = None

        # DP NOTE: not loading ExternalCalls because when initialized it
        #          does DNS lookups of the bastion and vault instances
        #          which we don't want to happen right now
        #if module.session and module.SSH_KEY:
        #    module.call = ExternalCalls(module)
        #else:
        #    module.call = None

        module.names = AWSNames(module)

        return module
    except ImportError:
        print("Could not import file 'config/{}'".format(config))
        return None

def valid_bosslet(bosslet):
    return load_configs().get(bosslet) is not None

class BossConfiguration(object):
    def __init__(self, bosslet, **kwargs):
        self.bosslet = bosslet

        self.cf_config = kwargs.get('cf_config')
        self.ami_version = kwargs.get('ami_version', 'latest')
        self.disable_preview = kwargs.get('disable_preview')

    def __getattr__(self, attr):
        return  getattr(self[self.cf_config], attr)

    def __getitem__(self, cf_config):
        if cf_config:
            warnings.warn("Use of cf_config is unsupported at this time")
        return load_config(self.bosslet, cf_config)

    def get(self, key, default=None):
        try:
            return self.__getattr__(key)
        except AttributeError:
            return default

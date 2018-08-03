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
import glob

from boto3.session import Session

from . import exceptions
from . import constants as const
from .external import ExternalCalls
from .ssh import SSHTarget
from .utils import keypair_to_file
from .names import AWSNames

CONFIGS_GLOB = const.repo_path('config', '*.py')

def valid_bosslet(bosslet_name):
    return bosslet_name in list_bosslets()

def list_bosslets():
    return [os.path.basename(f)[:-3] for f in glob.glob(CONFIGS_GLOB)]

class BossConfiguration(object):
    def __init__(self, bosslet, **kwargs):
        self.bosslet = bosslet

        self.ami_version = kwargs.get('ami_version', 'latest')
        self.disable_preview = kwargs.get('disable_preview')

        # Import the bosslet configuration file
        try:
            self.config = importlib.import_module('config.' + bosslet)
        except ImportError:
            raise exceptions.BossManageError("Problem importing 'config/{}.py'".format(bosslet))
        # Create the session object
        if self.config.PROFILE:
            self.session = Session(profile_name = self.config.PROFILE,
                                   region_name = self.config.REGION)
        else:
            self.session = None

        # Load outbound bastion information in one location
        if self.config.OUTBOUND_BASTION:
            keyfile = keypair_to_file(self.config.OUTBOUND_KEY)
            if not os.path.exists(keyfile):
                raise ValueError("OUTBOUND_KEY '{}' doesn't exist".format(keyfile))
            self.outbound_bastion = SSHTarget(keyfile,
                                              self.config.OUTBOUND_IP,
                                              self.config.OUTBOUND_PORT,
                                              self.config.OUTBOUND_USER)
        else:
            self.outbound_bastion = None

        # Load ssh key path in one location
        if self.config.SSH_KEY:
            keyfile = keypair_to_file(self.config.SSH_KEY)
            if not os.path.exists(keyfile):
                raise ValueError("SSH_KEY '{}' doesn't exist".format(keyfile))
            self.ssh_key = keyfile
        else:
            self.ssh_key = None

        # DP NOTE: Delayed loading of ExternalCalls because when intialized
        #          it does DNS lookupss fo the bastion and vault instances
        #          which will fail unless the core config has been launched
        if self.session and self.ssh_key:
            self._call = False
        else:
            self._call = None

        self.names = AWSNames(self)

    @property
    def call(self):
        if self._call is False:
            self._call = ExternalCalls(self)
        return self._call

    def __getattr__(self, attr):
        return  getattr(self.config, attr)

    def get(self, key, default=None):
        try:
            return self.__getattr__(key)
        except AttributeError:
            return default

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
from argparse import ArgumentParser

from boto3.session import Session

from . import exceptions
from . import constants as const
from .external import ExternalCalls
from .ssh import SSHTarget
from .aws import machine_lookup
from .utils import keypair_to_file, parse_hostname
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
            self._config = importlib.import_module('config.' + bosslet)
        except ImportError:
            raise exceptions.BossManageError("Problem importing 'config/{}.py'".format(bosslet))
        # Create the session object
        if self._config.PROFILE:
            self.session = Session(profile_name = self._config.PROFILE,
                                   region_name = self._config.REGION)
        else:
            self.session = None

        # Load outbound bastion information in one location
        if self._config.OUTBOUND_BASTION:
            keyfile = keypair_to_file(self._config.OUTBOUND_KEY)
            if not os.path.exists(keyfile):
                raise ValueError("OUTBOUND_KEY '{}' doesn't exist".format(keyfile))
            self.outbound_bastion = SSHTarget(keyfile,
                                              self._config.OUTBOUND_IP,
                                              self._config.OUTBOUND_PORT,
                                              self._config.OUTBOUND_USER)
        else:
            self.outbound_bastion = None

        # Load ssh key path in one location
        if self._config.SSH_KEY:
            keyfile = keypair_to_file(self._config.SSH_KEY)
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
        return  getattr(self._config, attr)

    def get(self, key, default=None):
        try:
            return self.__getattr__(key)
        except AttributeError:
            return default

    def __repr__(self):
        return "BossConfiguration('{}')".format(self.bosslet)

class BossParser(ArgumentParser):
    """A custom argument parser that provides common handling of looking up a
    specific hostname
    """
    _bosslet = False
    _hostname = False

    def add_hostname(self, private_ip = False, help = "Hostname of the target EC2 instance"):
        """Called to add arguments to the parser

        Can be automatically called by the constructor by passing add_hostname=True

        Adds '--private-ip', '--bosslet', and 'hostname' arguments to the parser

        Args:
            private_ip (bool) : If the '--private-ip' flag is allowed
        """
        self._hostname = True
        self._private_ip = private_ip
        if self._bosslet:
            raise Exception("Cannot add_hostname and add_bosslet")

        if self._private_ip:
            self.add_argument("--private-ip", "-p",
                              action='store_true',
                              default=False,
                              help = "If the hostname is an AWS IP address instead of an EC2 instance name")
        self.add_argument("--bosslet",
                          metavar = "BOSSLET",
                          choices = list_bosslets(),
                          default=None,
                          help="Bosslet in which the machine is running")
        self.add_argument("hostname", help = help)

    def add_bosslet(self, help = "Name of the target Bosslet configuration"):
        """Called to add arguments to the parser

        Can be automatically called by the constructor by passing add_bosslet=True

        Adds 'bosslet_name' argument to the parser
        """
        self._bosslet = True
        if self._hostname:
            raise Exception("Cannot add_bosslet and add_hostname")

        self.add_argument("bosslet_name",
                          metavar = "bosslet_name",
                          choices = list_bosslets()
                          help = help)

    def parse_args(self, *args, **kwargs):
        """Calls the underlying 'parse_args()' method and then handles resolving
        the AWS hostname and building the BossConfiguration.

        This method will add 'bosslet_config' as a variable on the returned object
        containing the BossConfiguration for the given bosslet.

        This method will exit will usage message and error message if an invalid
        combination of arguements have been given.
        """
        a = super().parse_args(*args, **kwargs)

        if self._bosslet:
            a.bosslet_config = BossConfiguration(a.bosslet_name)

        elif self._hostname:
            finished = False
            if self._private_ip:
                if a.private_ip:
                    if not a.bosslet:
                        self.print_usage()
                        print("Error: --bosslet required if --private-ip is used")
                        sys.exit(1)
                    else:
                        a.bosslet_config = BossConfiguration(a.bosslet)
                        a.ip = a.hostname
                        finished = True

            if not finished:
                idx, machine, bosslet_name = parse_hostname(a.hostname)

                if not bosslet_name and not a.bosslet:
                    self.print_usage()
                    print("Error: could not parse out bosslet name, include --bosslet")
                    sys.exit(1)
                elif bosslet_name and a.bosslet:
                    if bosslet_name != a.bosslet:
                        print("Error: two different bosslet names were specified, remove one")
                        sys.exit(1)
                elif a.bosslet:
                    bosslet_name = a.bosslet

                bosslet_config = BossConfiguration(bosslet_name)
                hostname = bosslet_config.names.dns[machine]
                if idx is not None:
                    hostname = str(idx) + "." + hostname

                a.bosslet = bosslet_name
                a.bosslet_config = bosslet_config
                a.hostname = hostname

                if self._private_ip: # only lookup IP if we allow specifying a private ip
                    ip = machine_lookup(bosslet_config.session, hostname, public_ip=False)
                    if not ip:
                        sys.exit(1) # machine_lookup() already printed an error message

                    a.ip = ip

        return a

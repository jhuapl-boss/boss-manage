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
import itertools
from argparse import ArgumentParser
from pprint import pformat

from boto3.session import Session

from . import exceptions
from . import constants as const
from . import console
from .external import ExternalCalls
from .ssh import SSHTarget
from .aws import machine_lookup
from .utils import keypair_to_file, parse_hostname
from .names import AWSNames

CONFIGS_GLOBS = [const.repo_path('config', '*.py'),
                 const.repo_path('config', 'custom', '*.py')]
CONFIGS_FMTS = [const.repo_path('config', '{}.py'),
                const.repo_path('config', 'custom', '{}.py')]

def valid_bosslet(bosslet_name):
    return bosslet_name in list_bosslets()

def list_bosslets():
    return [os.path.basename(f)[:-3].replace('_','.')
            for f in itertools.chain(*[glob.glob(g) for g in CONFIGS_GLOBS])]

class BossConfiguration(object):
    __EXPECTED_KEYS = [
        'EXTERNAL_DOMAIN',
        'EXTERNAL_FORMAT', # Optional
        'INTERNAL_DOMAIN',
        'NETWORK', # Optional
        'SUBNET_CIDR', # Optional
        'AMI_SUFFIX',
        'AMI_VERSION', # Optional
        'SCENARIO', # Optional, no default
        'VERIFY_SSL', # Optional
        'AUTH_RDS',
        'LAMBDA_BUCKET',
        'LAMBDA_SERVER',
        'LAMBDA_SERVER_KEY',
        'REGION',
        'AVAILABILITY_ZONE_USAGE', # Optional
        'ACCOUNT_ID',
        'PROFILE', # Optional
        'OUTBOUND_BASTION',
        'OUTBOUND_IP', # Conditional
        'OUTBOUND_PORT', # Conditional
        'OUTBOUND_USER', # Conditional
        'OUTBOUND_KEY', # Conditional
        'HTTPS_INBOUND', # Optional
        'SSH_INBOUND',
        'SSH_KEY',
        'BILLING_TOPIC', # Optional
        'BILLING_THRESHOLDS', # Conditional, required if setting up account
        'BILLING_CURRENCY', # Optional
        'ALERT_TOPIC', # Optional
    ]

    __DEFAULTS = {
        "EXTERNAL_FORMAT": "{machine}",
        "NETWORK": "10.0.0.0/16",
        "SUBNET_CIDR": 24,
        "AMI_VERSION": "latest",
        "VERIFY_SSL": True,
        "AVAILABILITY_ZONE_USAGE": {},
        "OUTBOUND_BASTION": False,
        "HTTPS_INBOUND": "0.0.0.0/0",
        "BILLING_TOPIC": "BossBillingList",
        "BILLING_CURRENCY": "USD",
        "ALERT_TOPIC": "BossMailingList",
    }

    def __init__(self, bosslet, **kwargs):
        self.bosslet = bosslet

        # Import the bosslet configuration file
        try:
            bosslet = bosslet.replace('.','_')
            prefix = const.repo_path()

            for fmt in CONFIGS_FMTS:
                path = fmt.format(bosslet)
                if os.path.exists(path):
                    # Translate the file path into a module import reference
                    mod = path.replace(prefix, '').replace('/', '.')[1:-3]
                    self._config = importlib.import_module(mod)
                    break
            else:
                raise ValueError("Cannot located Bosslet '{}'".format(self.bosslet))
        except ImportError:
            raise exceptions.BossManageError("Problem importing '{}'".format(mod))

        if not self.verify():
            raise exceptions.BossManageError("Bosslet config is not valid")

        # Handle keyword arguments
        self.disable_preview = kwargs.get('disable_preview')

        self.ami_version = self.get('AMI_VERSION')
        if kwargs.get('ami_version') is not None:
            self.ami_version = kwargs['ami_version']

        self.scenario = self.get('SCENARIO')
        if kwargs.get('scenario') is not None:
            self.scenario = kwargs['scenario']


        # Create the session object
        self.session = Session(profile_name = self.get('PROFILE'),
                               region_name = self._config.REGION)
        if self.session.get_credentials() is None:
            console.warning("Could not located AWS credentials")
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

        self.names = AWSNames.from_bosslet(self)

        # Use __getattr__ to get the __DEFAULT value if not specified
        if not self.VERIFY_SSL:
            import ssl
            ssl._create_default_https_context = ssl._create_unverified_context

    def __getattr__(self, attr):
        if hasattr(self._config, attr):
            return getattr(self._config, attr)
        elif attr in self.__DEFAULTS:
            return self.__DEFAULTS[attr]
        elif attr == 'call':
            # DP NOTE: Delayed loading of ExternalCalls because when intialized
            #          it does DNS lookupss fo the bastion and vault instances
            #          which will fail unless the core config has been launched
            if self.session is None:
                raise AttributeError("Require an AWS session to use ExternalCalls")
            if self.ssh_key is None:
                raise AttributeError("Require a SSH key to use ExternalCalls")

            # Using __getattr__ instead of an @property because if an
            # @property raises an AttributeError then __getattr__ gets
            # called.
            self.call = ExternalCalls(self) # saving as self.call for future lookups
            return self.call
        else:
            msg = "'{}' object has not attribute '{}'".format(self.__class__.__name__,
                                                              attr)
            raise AttributeError(msg)

    def get(self, key, default=None):
        try:
            return self.__getattr__(key)
        except AttributeError:
            return default

    def __repr__(self):
        return "BossConfiguration('{}')".format(self.bosslet)

    def verify(self, fh=sys.stdout):
        ret = True
        for key in self.__EXPECTED_KEYS:
            if not hasattr(self._config, key):
                if key not in self.__DEFAULTS:
                    if key in ('SCENARIO', 'BILLING_THRESHOLDS', 'PROFILE'):
                        pass
                    elif key in ('OUTBOUND_IP',
                                 'OUTBOUND_PORT',
                                 'OUTBOUND_USER',
                                 'OUTBOUND_KEY') and \
                         self.get('OUTBOUND_BASTION') == False:
                        pass
                    else:
                        console.error("Variable '{}' not defined".format(key), file=fh)
                        ret = False

        for key in dir(self._config):
            if key not in self.__EXPECTED_KEYS:
                if not key.startswith('__'):
                    console.warning("Extra variable '{}' defined".format(key), file=fh)

        return ret

    def display(self, fh = sys.stdout):
        for key in self.__EXPECTED_KEYS:
            try:
                val = pformat(self.__getattr__(key))
                print("{} = {}".format(key, val), file=fh)
            except AttributeError:
                if key in ('SCENARIO', 'BILLING_THRESHOLDS', 'PROFILE'):
                    pass
                elif key in ('OUTBOUND_IP',
                             'OUTBOUND_PORT',
                             'OUTBOUND_USER',
                             'OUTBOUND_KEY') and \
                     self._config.OUTBOUND_BASTION == False:
                    pass
                else:
                    raise

def create_help(header, options):
    """Create formated help

    Args:
        header (str): The header for the help
        options (list[str]): The options that are available for argument

    Returns:
        str: Formated argument help
    """
    return "\n" + header + "\n" + \
           "\n".join(map(lambda x: "  " + x, options)) + "\n"

class BossParser(ArgumentParser):
    """A custom argument parser that provides common handling of looking up a
    specific hostname
    """
    _bosslet = False
    _hostname = False
    __subparsers = {}

    def __init__(self, *args, **kwargs):
        if 'help' in kwargs:
            # Remove 'help' from the arguments, as it is a valid keyword argument
            # for subparsers, but not the initial parser
            del kwargs['help']

        super().__init__(*args, **kwargs)

    def create_subparser(self, dest, **kwargs):
        """Create a subparser definition that can be populated with `add_subcommand()`

        Args:
            dest (str): The name of the argument where the selected subcommand is stored
            kwargs (dict): Any other arguments for the `add_subparser()` call
        """
        subparser = self.add_subparsers(dest=dest,
                                        parser_class=BossParser,
                                        **kwargs)
        subparser.required = True

        self.__subparsers[dest] = subparser

    def add_subcommand(self, dest, subcommand):
        """Add a subcommand to a previously defined subparser

        Args:
            dest (str): The `dest` value passed to `create_subparser()`
            subcommand (str): The name of the subcommand that is being defined

        Returns:
            function: A function that acts like BossParser and can be used to
                      to create the parser for the given subcommand
        """
        def add_parser(**kwargs):
            # BossParser / ArgumentParser __init__ doesn't have a 'help' argument
            # but a sub-parser requires 'help' for it to be displayed in --help
            if 'description' in kwargs and 'help' not in kwargs:
                kwargs['help'] = kwargs['description']
            return self.__subparsers[dest].add_parser(subcommand, **kwargs)
        return add_parser

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
                          choices = list_bosslets(),
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

        # Note: Using `'<variable>' in a` instead of using the self._bosslet
        #       or self._hostname variables because with a nested parser the
        #       parent parser will not see those variables for the subparser

        # Note: Using `self.print_usage()` will not necessarly print the correct
        #       usage if the problem is with arguments from a subparser

        try:
            if 'bosslet_name' in a:
                a.bosslet_config = BossConfiguration(a.bosslet_name)

            elif  'hostname' in a:
                finished = False
                if 'private_ip' in a:
                    if a.private_ip:
                        if not a.bosslet:
                            msg = "--bosslet required if --private-ip is used"
                            self.error(msg)
                        else:
                            a.bosslet_config = BossConfiguration(a.bosslet)
                            a.ip = a.hostname
                            finished = True

                if not finished:
                    idx, machine, bosslet_name = parse_hostname(a.hostname)

                    if not bosslet_name and not a.bosslet:
                        msg = "Could not parse out bosslet name, include --bosslet"
                        self.error(msg)
                    elif bosslet_name and a.bosslet:
                        if bosslet_name != a.bosslet:
                            msg = "Two different bosslet names were specified, remove one"
                            self.error(msg)
                    elif a.bosslet:
                        bosslet_name = a.bosslet

                    bosslet_config = BossConfiguration(bosslet_name)
                    hostname = bosslet_config.names[machine].dns
                    if idx is not None:
                        hostname = str(idx) + "." + hostname

                    a.bosslet_name = bosslet_name
                    a.bosslet_config = bosslet_config
                    a.hostname = hostname

                    if self._private_ip: # only lookup IP if we allow specifying a private ip
                        ip = machine_lookup(bosslet_config.session, hostname, public_ip=False)
                        if not ip:
                            sys.exit(1) # machine_lookup() already printed an error message

                        a.ip = ip

            return a
        except exceptions.BossManageError as ex: # BossConfig import or verification error
            self.error(ex)
        except ValueError as ex: # Invalid Bosslet name
            self.error(ex)

class BossCLI(object):
    """Interface for defining a CLI application / script"""
    def get_parser(self, ParentParser=BossParser):
        """Create and return the parser for this application

        Args:
            ParentParser: If this application is a subcommand ParentParser will
                          be the results from `BossParser.add_subcommand`. If
                          this is not provided, use BossParser.

        Returns:
            BossParser: The parser instance created and populated
        """
        raise NotImplemented()

    def run(self, args):
        """The main entrpoint for the application

        Args:
            args (Namespace): The parsed results for the application to use

        Returns:
            optional[int]: Return code
        """
        raise NotImplemented()

    def main(self): # just put into if __name__ ...
        """Application entrypoint that parsers the arguments and calls `run()`"""
        parser = self.get_parser()
        args = parser.parse_args()
        self.run(args)

class NestedBossCLI(BossCLI):
    """Implementation of a nested CLI
    A nested CLI contains common arguments and a set of subcommands that will be executed

    To use:
     * Define the COMMANDS, PARSER_ARGS, SUBPARSER_ARGS variables
     * Optionally implement the `add_common_arguments()` method

    Attributes:
        COMMANDS: Mapping of subcommands and the implementing BossCLI reference
        PARSER_ARGS: BossParser arguments
        SUBPARSER_ARGS: BossParser.create_subparser
                        The key 'dest' must be defined
    """
    COMMANDS = {
        # 'command_name': BossCLI,
    }

    PARSER_ARGS = {
        # 'description': '',
    }

    SUBPARSER_ARGS = {
        # 'dest': 'nested_command',
        # 'metavar': 'command',
        # 'help': 'nested commands',
    }

    def __init__(self):
        self.subcommands = { name: cli()
                             for name, cli in self.COMMANDS.items() }
        self.dest = self.SUBPARSER_ARGS['dest']

    def add_common_arguments(self, parser):
        """Method for adding the common arguments for all of the nested commands

        Note: Called before add the subcommands so that non optional arguments
              will appear before the subcommands

        Args:
            parser (BossParser): Parser instance to add common arguments to
        """
        pass

    def get_parser(self, ParentParser=BossParser):
        self.parser = ParentParser(**self.PARSER_ARGS)
        self.add_common_arguments(self.parser)
        self.parser.create_subparser(**self.SUBPARSER_ARGS)
        for subcommand in self.subcommands.keys():
            parser_ = self.parser.add_subcommand(self.dest, subcommand)
            self.subcommands[subcommand].get_parser(parser_)

        return self.parser

    def run(self, args):
        return self.subcommands[getattr(args, self.dest)].run(args)

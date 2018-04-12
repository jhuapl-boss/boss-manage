#!/usr/bin/env python3

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

"""A driver script for creating AWS CloudFormation Stacks."""

import argparse
import sys
import os
import importlib
import glob

import alter_path
from lib import exceptions
from lib import aws
from lib import utils
from lib import configuration
from lib import constants
from lib.cloudformation import CloudFormationConfiguration
from lib.stepfunctions import heaviside

# Add a reference to boss-manage/lib/ so that we can import those files
cur_dir = os.path.dirname(os.path.realpath(__file__))
cf_dir = os.path.normpath(os.path.join(cur_dir, '..', 'cloud_formation'))
sys.path.append(cf_dir) # Needed for importing CF configs

def call_config(bosslet_config, config, func_name):
    """Import 'configs.<config>' and then call the requested function with
    <session> and <bosslet>.
    """
    module = importlib.import_module("configs." + config)

    if func_name in module.__dict__:
        module.__dict__[func_name](bosslet_config)
    elif func_name == 'delete':
        # TODO load stack name
        CloudFormationConfiguration(config, bosslet_config).delete()
    else:
        print("Configuration '{}' doesn't implement function '{}'".format(config, func_name))

if __name__ == '__main__':
    os.chdir(os.path.join(cur_dir, "..", "cloud_formation"))

    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    config_names = [x.split('/')[1].split('.')[0] for x in glob.glob("configs/*.py") if "__init__" not in x]
    config_help = create_help("config_name supports the following:", config_names)

    actions = ["create", "update", "delete", "post-init", "pre-init", "generate"]
    actions_help = create_help("action supports the following:", actions)

    scenarios = [x.split('/')[1].split('.')[0] for x in glob.glob("scenarios/*.yml")]
    scenario_help = create_help("scenario supports the following:", scenarios)

    parser = argparse.ArgumentParser(description = "Script the creation and provisioning of CloudFormation Stacks",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=actions_help + config_help + scenario_help)
    parser.add_argument("--ami-version",
                        metavar = "<ami-version>",
                        default = "latest",
                        help = "The AMI version to use when selecting images (default: latest)")
    parser.add_argument("--scenario",
                        metavar = "<scenario>",
                        choices = scenarios,
                        help = "The deployment configuration to use when creating the stack (instance size, autoscale group size, etc) (default: development)")
    parser.add_argument("--disable-preview",
                        action = "store_true",
                        help = "Disable update previews change sets (default: enable)"),
    parser.add_argument("action",
                        choices = actions,
                        metavar = "action",
                        help = "Action to execute")
    parser.add_argument("bosslet_name",
                        help="Bosslet in which to execute the configuration")
    parser.add_argument("config_name",
                        choices = config_names,
                        metavar = "config_name",
                        help="Configuration to act upon (imported from configs/)")

    args = parser.parse_args()

    if not configuration.valid_bosslet(args.bosslet_name):
        parser.print_usage()
        print("Error: Bosslet name '{}' doesn't exist in configs file ({})".format(args.bosslet_name, configuration.CONFIGS_PATH))
        sys.exit(1)

    os.environ["AMI_VERSION"] = args.ami_version
    os.environ["DISABLE_PREVIEW"] = str(args.disable_preview)

    constants.load_scenario(args.scenario)

    bosslet_config = configuration.BossConfiguration(args.bosslet_name,
                                                     #cf_config = args.config_name,
                                                     ami_version = args.ami_version,
                                                     disable_preview = args.disable_preview)

    try:
        func = args.action.replace('-','_')
        ret = call_config(bosslet_config, args.config_name, func)
        if ret == False:
            sys.exit(1)
        else:
            sys.exit(0)
    except exceptions.StatusCheckError as ex:
        target = 'the server'
        if hasattr(ex, 'target') and ex.target is not None:
            target = ex.target

        print()
        print(ex)
        print("Check networking and {}".format(target))
        print("Then run the following command:")
        print("\t" + utils.get_command("post-init"))
        sys.exit(2)
    except exceptions.KeyCloakLoginError as ex:
        print()
        print(ex)
        print("Check Vault and Keycloak")
        print("Then run the following command:")
        print("\t" + utils.get_command("post-init"))
        sys.exit(2)
    except heaviside.exceptions.CompileError as ex:
        print()
        print(ex)
        print()
        print("Fix the syntax error in {}".format(ex.source))
        print("Then run the following command:")
        print("\t" + utils.get_command("post-init"))
        sys.exit(2)
    except heaviside.exceptions.HeavisideError as ex:
        print()
        print("Heaviside Error: {}".format(ex))
        print("Fix the problem, then run the following command:")
        print("\t" + utils.get_command("post-init"))
        sys.exit(2)

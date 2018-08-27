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

def build_dependency_graph(bosslet_config, modules):
    class Node(object):
        """Directed Dependency Graph Node"""
        def __init__(self, name):
            self.name = name
            self.edges = []

        def __repr__(self):
            return "<Node: {}>".format(self.name)

        def depends_on(self, node):
            self.edges.append(node)

    def resolve(node, resolved, seen=None):
        """From a root node, add all sub elements and then the root"""
        if seen is None:
            seen = []
        seen.append(node)
        for edge in node.edges:
            if edge not in resolved:
                if edge in seen:
                    raise exceptions.CircularDependencyError(node.name, edge.name)
                resolve(edge, resolved, seen)
        resolved.append(node)

    nums = {} # Mapping of config to index in modules list
    nodes = {} # Mapping of config to Node
    no_deps = [] # List of configs that are not the target of a dependency
                 # meaning that they are the root of a dependency tree
    # Populate variables
    for i in range(len(modules)):
        config = modules[i][0]
        nums[config] = i
        nodes[config] = Node(config)
        no_deps.append(config)

    # lookup the existing stacks to so we can verify that all dependencies will
    # be satisfied (by either existing or being launched)
    client = bosslet_config.session.client('cloudformation')
    suffix = "".join([x.capitalize() for x in bosslet_config.INTERNAL_DOMAIN.split('.')])
    valid_status = ('UPDATE_COMPLETE', 'CREATE_COMPLETE')
    existing = [
        stack['StackName'][:-len(suffix)].lower()
        for stack in client.list_stacks()['StackSummaries']
        if stack['StackName'].endswith(suffix) and stack['StackStatus'] in valid_status
    ]

    # Create dependency graph and locate root nodes
    for config, module in modules:
        deps = module.__dict__.get('DEPENDENCIES')
        if deps is None:
            continue
        if type(deps) == str:
            deps = [deps]

        for dep in deps:
            if dep not in nodes:
                # dependency not part of configs to launch
                if dep not in existing:
                    raise exceptions.MissingDependencyError(config, dep)
            else:
                nodes[config].depends_on(nodes[dep])
                try:
                    no_deps.remove(dep)
                except:
                    pass # Doesn't exist in no_deps list

    # Resolve dependency graph
    resolved = []
    for no_dep in no_deps: # Don't have any dependencies
        resolve(nodes[no_dep], resolved)

    # Reorder input
    reordered = [ modules[nums[node.name]] for node in resolved ]

    # Extra check
    if len(reordered) != len(modules):
        raise exceptions.CircularDependencyError()

    return reordered


def call_configs(bosslet_config, configs, func_name):
    """Import 'configs.<config>' and then call the requested function with
    <session> and <bosslet>.
    """
    modules = [(config, importlib.import_module("configs." + config)) for config in configs]

    modules = build_dependency_graph(bosslet_config, modules)
    if func_name == 'delete':
        modules.reverse()

    print("Execution Order:")
    for config, module in modules:
        print("\t{}".format(config))

    for config, module in modules:
        print()
        print("======================================================================")
        print("== Working on {}".format(config))
        try:
            if func_name in module.__dict__:
                resp = module.__dict__[func_name](bosslet_config)
            elif func_name == 'delete':
                resp = CloudFormationConfiguration(config, bosslet_config).delete()
            else:
                print("Configuration '{}' doesn't implement function '{}', skipping".format(config, func_name))
                resp = True

            if resp is False:
                print("Problem with {} {}, exiting early".format(config, func_name))
                return False
        except:
            msg = "== Error with {} {}".format(config, func_name)
            print(msg)
            print()
            raise

    return True

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
                        metavar = "bosslet_name",
                        choices = configuration.list_bosslets(),
                        help="Bosslet in which to execute the configuration")
    parser.add_argument("config_name",
                        choices = ['all', *config_names],
                        metavar = "config_name",
                        nargs = "+",
                        help="Configuration to act upon (imported from configs/)")

    args = parser.parse_args()

    constants.load_scenario(args.scenario)

    bosslet_config = configuration.BossConfiguration(args.bosslet_name,
                                                     ami_version = args.ami_version,
                                                     disable_preview = args.disable_preview)

    if args.config_name == ['all']:
        configs = config_names
    else:
        configs = args.config_name

    try:
        func = args.action.replace('-','_')
        ret = call_configs(bosslet_config, configs, func)
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
    except exceptions.BossManageError as ex:
        print()
        print("Boss Manage Error: {}".format(ex))
        sys.exit(2)

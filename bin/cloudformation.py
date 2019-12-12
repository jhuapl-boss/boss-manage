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
import traceback

import alter_path
from lib import exceptions
from lib import aws
from lib import utils
from lib import configuration
from lib import constants
from lib import console
from lib.cloudformation import CloudFormationConfiguration
from lib.migrations import MigrationManager
from lib.stepfunctions import heaviside

# Add a reference to boss-manage/lib/ so that we can import those files
cur_dir = os.path.dirname(os.path.realpath(__file__))
cf_dir = os.path.normpath(os.path.join(cur_dir, '..', 'cloud_formation'))
sys.path.append(cf_dir) # Needed for importing CF configs

def build_dependency_graph(action, bosslet_config, modules):
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
    existing = { k : v['StackStatus']
                 for k, v in aws.get_existing_stacks(bosslet_config).items() }

    stop = False
    for name, status in existing.items():
        if status.endswith('_IN_PROGRESS'):
            console.warning("Config '{}' is in progress".format(name))
            stop = True
        elif status.endswith('_FAILED'):
            if name not in nodes:
                console.fail("Config '{}' is failed and should be acted upon".format(name))
                stop = True
            else:
                if action == 'delete':
                    console.info("Config '{}' is failed, deleting".format(name))
                elif status == 'UPDATE_ROLLBACK_FAILED':
                    console.fail("Config '{}' needs to be manually resolved in the AWS console".format(name))
                    stop = True
                else: # CREATE, DELETE, or ROLLBACK FAILED
                    console.fail("Config '{}' is failed, needs to be deleted".format(name))
                    stop = True
    if stop:
        raise exceptions.BossManageError('Problems with existing stacks')

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
                if dep not in existing and action == "create":
                    raise exceptions.MissingDependencyError(config, dep)
            else:
                # If action is update, post-init, pre-init, verify that
                # the config is already existing
                if action not in ('create', 'delete') and dep not in existing:
                    raise exceptions.MissingDependencyError(config, dep)

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

    # Removed configs that don't need to be created
    if action == "create":
        for config, module in reordered[:]:
            if config in existing:
                # If the config already exists, don't try to create it again
                reordered.remove((config, module))

    # Remove configs that don't need to be deleted / updated / etc
    else:
        for config, module in reordered[:]:
            if config not in existing:
                # If the config doesn't exist, don't try to delete it again
                # If the config doesn't exist, don't try to update it
                reordered.remove((config, module))

        if action == "delete": # Delete in reverse order
            reordered.reverse()

    # Make sure that the target configs are not currently being processed
    for config, module in reordered:
        if config in existing and existing[config].endswith("_IN_PROGRESS"):
            raise exceptions.DependencyInProgressError(config)

    return reordered


def call_configs(bosslet_config, configs, func_name):
    """Import 'configs.<config>' and then call the requested function with
    <session> and <bosslet>.
    """
    modules = [(config, importlib.import_module("configs." + config)) for config in configs]

    if func_name != 'generate':
        modules = build_dependency_graph(func_name, bosslet_config, modules)

    print("Execution Order:")
    for config, module in modules:
        print("\t{}".format(config))

    with console.status_line(spin=True, print_status=True) as status:
        for config, module in modules:
            print()
            status('Working on {}'.format(config))

            if func_name in module.__dict__:
                module.__dict__[func_name](bosslet_config)
            elif func_name == 'delete':
                CloudFormationConfiguration(config, bosslet_config).delete()
            else:
                print("Configuration '{}' doesn't implement function '{}', skipping".format(config, func_name))

def update_migrate(bosslet_config, config):
    migration_progress = constants.repo_path("cloud_formation", "configs", "migrations", config, "progress")

    if not os.path.exists(migration_progress):
        console.info("No migrations to apply")
        return

    with open(migration_progress, "r") as fh:
        cur_ver = int(fh.read())

    new_ver = CloudFormationConfiguration(config, bosslet_config).existing_version()

    migrations = MigrationManager(config, cur_ver, new_ver)
    if not migrations.has_migrations:
        console.info("No migrations to apply")
        os.remove(migration_progress)
        return

    def callback(migration_file):
        with open(migration_progress, 'w') as fh:
            fh.write(str(migration_file.stop))

    migrations.add_callback(post=callback)

    migrations.post_update(bosslet_config)

    os.remove(migration_progress)

if __name__ == '__main__':
    os.chdir(os.path.join(cur_dir, "..", "cloud_formation"))

    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    config_names = [x.split('/')[1].split('.')[0] for x in glob.glob("configs/*.py") if "__init__" not in x]
    config_help = create_help("config_name supports the following:", config_names)

    actions = ["create", "update", "delete", "post-init", "pre-init", "update-migrate", "generate"]
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

    try:
        bosslet_config = configuration.BossConfiguration(args.bosslet_name,
                                                         disable_preview = args.disable_preview,
                                                         ami_version = args.ami_version,
                                                         scenario = args.scenario)

        constants.load_scenario(bosslet_config.scenario)

        if args.config_name == ['all']:
            configs = config_names
        else:
            configs = args.config_name

        if args.action == "update-migrate":
            if len(configs) > 1:
                raise exceptions.BossManageError("Can only apply update migrations to a single config")
            update_migrate(bosslet_config, configs[0])
            sys.exit(0)

        func = args.action.replace('-','_')
        call_configs(bosslet_config, configs, func)
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
    except exceptions.VaultError as ex:
        print()
        print(ex)
        print("Check Vault")
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
        if ex.causes is not None:
            for cause in ex.causes:
                print("\t", cause)
        sys.exit(2)
    except Exception as ex:
        print()
        # suppress the printing of multiple chained exceptions, just the current one
        traceback.print_exc(chain=False)
        sys.exit(1)

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

import argparse
import sys
import os
import glob
import shlex
import subprocess
from distutils.spawn import find_executable

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.environ["PATH"] += ":" + os.path.join(REPO_ROOT, "bin")

def get_commit():
    cmd = "git rev-parse HEAD"
    result = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE)
    return result.stdout.decode("utf-8").strip()

def execute(cmd, output_file):
    return subprocess.Popen(shlex.split(cmd), stderr=subprocess.STDOUT, stdout=open(output_file, "w"))

if __name__ == '__main__':
    for cmd in ("git", "packer"):
        if find_executable(cmd) is None:
            print("Could not locate {} binary on the system, required...".format(cmd))
            sys.exit(1)

    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    git_hash = get_commit()

    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    config_glob = os.path.join(REPO_ROOT, "packer", "variables", "*")
    config_names = [x.split(os.path.sep)[-1] for x in glob.glob(config_glob)]
    config_help_names = list(config_names)
    config_help_names.append("all")
    config_help = create_help("config is on of the following:", config_help_names)

    parser = argparse.ArgumentParser(description = "Script the building of machines images using Packer and SaltStack",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=config_help)
    parser.add_argument("--single-thread",
                        action = "store_true",
                        default = False,
                        help = "Only build one config at a time. (default: Build all configs at the same time)")
    parser.add_argument("--only",
                        metavar = "<packer-builder>",
                        default = "amazon-ebs",
                        help = "Which Packer building to use. (default: amazon-ebs)")
    parser.add_argument("--name",
                        metavar = "<build name>",
                        default = 'h' + git_hash[:8],
                        help = "The build name for the machine image(s). (default: First 8 characters of the git SHA1 hash)")
    parser.add_argument("--no-bastion",
                        action = "store_false",
                        default = True,
                        dest="bastion",
                        help = "Don't use the aws-bastion file when building. (default: Use the bastion)")
    parser.add_argument("config",
                        choices = config_help_names,
                        metavar = "<config>",
                        nargs = "+",
                        help="Packer variable to build a machine image for")

    args = parser.parse_args()

    if "all" in args.config:
        args.config = config_names

    bastion_config = "-var-file=" + os.path.join(REPO_ROOT, "config", "aws-bastion")
    credentials_config = os.path.join(REPO_ROOT, "config", "aws-credentials")
    packer_file = os.path.join(REPO_ROOT, "packer", "vm.packer")

    if not os.path.exists(credentials_config):
        print("Could not locate AWS credentials file at '{}', required...".format(credentials_config))
        sys.exit(1)

    packer_logs = os.path.join(REPO_ROOT, "packer", "logs")
    if not os.path.isdir(packer_logs):
        os.mkdir(packer_logs)

    cmd = """{packer} build
             {bastion} -var-file={credentials}
             -var-file={machine} -var 'name_suffix={name}'
             -var 'commit={commit}' -var 'force_deregister={deregister}'
             -only={only} {packer_file}"""
    cmd_args = {
        "packer" : "packer",
        "bastion" : bastion_config if args.bastion else "",
        "credentials" : credentials_config,
        "only" : args.only,
        "packer_file" : packer_file,
        "name" : "-" + args.name,
        "commit" : git_hash,
        "deregister" : "true" if args.name == "test" else "false",
        "machine" : "" # replace for each call
    }

    procs = []
    for config in args.config:
        print("Launching {} configuration".format(config))
        log_file = os.path.join(packer_logs, config + ".log")
        cmd_args["machine"] = os.path.join(REPO_ROOT, "packer", "variables", config)
        proc = execute(cmd.format(**cmd_args), log_file)

        if args.single_thread:
            print("Waiting for build to finish")
            proc.wait()
        else:
            procs.append(proc)

    try:
        print("Waiting for all builds started to finish")
        for proc in procs:
            proc.wait()
    except KeyboardInterrupt: # <CTRL> + c
        print("Killing builds")
        for proc in procs:
            proc.poll()
            if proc.returncode is None:
                proc.kill()
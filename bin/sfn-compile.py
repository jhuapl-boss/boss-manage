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
import os
import sys
from pathlib import Path

import alter_path
from lib.stepfunctions import heaviside

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = "Script to compile a heaviside file into a StepFunction State Machine",
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", "-o",
                        metavar = "<file>",
                        default = sys.stdout,
                        type = argparse.FileType('w'),
                        help = "Location to save the StepFunction State Machine to (default: stdout)")
    parser.add_argument("--region", "-r",
                        metavar = "<aws_region>",
                        default = '',
                        help = "AWS Region for ARNs (default: '')")
    parser.add_argument("--account", "-a",
                        metavar = "<aws_account>",
                        default = '',
                        help = "AWS Account ID for ARNs (default: '')")
    parser.add_argument("file",
                        help="heaviside file to compile")

    args = parser.parse_args()

    try:
        machine = heaviside.compile(Path(args.file),
                                    translate = heaviside.create_translate(args.region, args.account),
                                    indent=3)
        args.output.write(machine)
        sys.exit(0)
    except heaviside.exceptions.CompileError as ex:
        print(ex)
        sys.exit(1)

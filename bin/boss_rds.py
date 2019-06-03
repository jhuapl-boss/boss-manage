#!/usr/bin/env python3

# Copyright 2019 The Johns Hopkins University Applied Physics Laboratory
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

"""A script for manipulating the BOSS' RDS from the endpoint instance.

COMMANDS : A dictionary of available commands and the functions to call
"""

import argparse
import sys, os
import boto3
import logging
import alter_path

from lib import aws
from lib import boss_rds

COMMANDS = {
    "sql-list": boss_rds.sql_list,
    "sql-resource-lookup": boss_rds.sql_resource_lookup_key,
    "sql-coord-frame-lookup": boss_rds.sql_coordinate_frame_lookup_key,
}

if __name__ == '__main__':
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    commands = list(COMMANDS.keys())
    commands_help = create_help("command supports the following:", commands)

    parser = argparse.ArgumentParser(description = "Script for manipulating endpoint instances",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=commands_help)
    parser.add_argument("--aws-credentials", "-a",
                        metavar = "<file>",
                        default = os.environ.get("AWS_CREDENTIALS"),
                        type = argparse.FileType('r'),
                        help = "File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("--quiet", "-q",
                        action='store_true',
                        default=False,
                        help='Run the script quietly, no print statements will be displayed.')
    parser.add_argument("domain",
                    help="Domain in which to execute the configuration (example: subnet.vpc.boss)")
    parser.add_argument("command",
                        choices = commands,
                        metavar = "command",
                        help = "Command to execute")
    parser.add_argument("arguments",
                        nargs = "*",
                        help = "Arguments to pass to the command")

    args = parser.parse_args()

    #Check AWS configurations
    if args.aws_credentials is None:
        parser.print_usage()
        logging.error("AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    # specify AWS keys, sets up connection to the client.
    session = aws.create_session(args.aws_credentials)

    # COnfigure logging if verbose
    if not args.quiet:
        logging.basicConfig(level=logging.INFO)
        
    if args.command in COMMANDS:
        COMMANDS[args.command](session, args.domain, *args.arguments)
    else:
        parser.print_usage()
        sys.exit(1)
    



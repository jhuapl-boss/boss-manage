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

import sys, os
import logging
import alter_path

from lib import boss_rds
from lib import configuration

COMMANDS = {
    "sql-tables":boss_rds.sql_tables,
    "sql-list": boss_rds.sql_list,
    "sql-resource-lookup": boss_rds.sql_resource_lookup_key,
    "sql-coord-frame-lookup": boss_rds.sql_coordinate_frame_lookup_key,
    "sql-job-ids-lookup": boss_rds.sql_channel_job_ids,
}
HELP = {
    "sql-tables",
    "sql-list",
    "sql-resource-lookup <coll/exp/chan> | <coll/exp> | <coll>",
    "sql-coord-frame-lookup <coordinate_frame>",
    "sql-job-ids-lookup <coll/exp/channel>",
}

if __name__ == '__main__':
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    commands = list(COMMANDS.keys())
    instructions = list(HELP)
    commands_help = create_help("command supports the following:", instructions)
    
    parser = configuration.BossParser(description = "Script for manipulating endpoint instances",
                                      formatter_class=argparse.RawDescriptionHelpFormatter,
                                      epilog=commands_help)
    parser.add_argument("--quiet", "-q",
                        action='store_true',
                        default=False,
                        help='Run the script quietly, no print statements will be displayed.')
    parser.add_bosslet()
    parser.add_argument("command",
                        choices = commands,
                        metavar = "command",
                        help = "Command to execute")
    parser.add_argument("arguments",
                        nargs = "*",
                        help = "Arguments to pass to the command")

    args = parser.parse_args()

    # Configure logging if verbose
    if not args.quiet:
        logging.basicConfig(level=logging.INFO)
        
    if args.command in COMMANDS:
        COMMANDS[args.command](args.bosslet_config, *args.arguments)
    else:
        parser.print_usage()
        sys.exit(1)
    



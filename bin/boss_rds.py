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

def sql_list(session, domain, db_table):
    """
    List all the available members of a given sql table.

    Args:
        session (Session): Open boto3 session.
        domain (str): VPC such as integration.boss.
        db_table: Identifies which table members to list.

    Returns:
        (str): Lookup key.
    """
    query = "SELECT * FROM {}".format(db_table)

    logging.info('Tunneling to DB (slow) . . .')
    with boss_rds.connect_rds(session, domain) as sql:
        try:
            cursor = sql.cursor()
            cursor.execute(query)
            ans = cursor.fetchall()
            for i in ans:
                logging.info(i)
        finally:
            cursor.close()

def sql_resource_lookup_key(session, domain, resource_params):
    """
    Get the lookup key that identifies the resource from the database.

    Args:
        session (Session): Open boto3 session.
        domain (str): VPC such as integration.boss.
        resource_params (str): Identifies collection, experiment or channel.

    Returns:
        (str): Lookup key.
    """
    collection, experiment, channel = None, None, None
    resource = resource_params.split("/")
    
    if len(resource) == 0:
        raise Exception("Incorrect number of arguments(Make sure the resource provided has at least a collection to lookup)")
    else:
        if len(resource) > 0:
            collection = resource_params.split("/")[0]
        if len(resource) > 1:
            experiment = resource_params.split("/")[1]
        if len(resource) > 2:
            channel = resource_params.split("/")[2]
        elif len(resource) > 3:
            raise Exception("Only provide /coll/exp/chan")

    coll_query = "SELECT id FROM collection WHERE name = %s"
    exp_query = "SELECT id FROM experiment WHERE name = %s"
    chan_query = "SELECT id FROM channel WHERE name = %s"

    with boss_rds.connect_rds(session, domain) as sql:
        try:
            cursor = sql.cursor()
            if collection is not None:
                cursor.execute(coll_query, (collection,))
                coll_set = cursor.fetchall()
                if len(coll_set) != 1:
                    raise ResourceNotFoundException(
                        "Can't find collection: {}".format(collection))
                else:
                    cuboid_str = "{}&".format(coll_set[0][0])
                    logging.info("{} collection id: {}".format(collection, coll_set[0][0]))
            if experiment is not None:
                cursor.execute(exp_query, (experiment,))
                exp_set = cursor.fetchall()
                if len(exp_set) != 1:
                    raise ResourceNotFoundException(
                        "Can't find experiment: {}".format(experiment))
                else:
                    cuboid_str = cuboid_str + "{}&".format(exp_set[0][0])
                    logging.info("{} experiment id: {}".format(experiment, exp_set[0][0]))
            if channel is not None:
                cursor.execute(chan_query, (channel,))
                chan_set = cursor.fetchall()
                if len(chan_set) != 1:
                    raise ResourceNotFoundException(
                        "Can't find channel: {}".format(experiment))
                else:
                    cuboid_str = cuboid_str + "{}&".format(chan_set[0][0])
                    logging.info("{} channel id: {}".format(channel, chan_set[0][0]))
        finally:
            cursor.close()
    
    logging.info("Cuboid key: {} \n".format(cuboid_str))
    return cuboid_str

def sql_coordinate_frame_lookup_key(session, domain, coordinate_frame):
    """
    Get the lookup key that identifies the coordinate fram specified.

    Args:
        session (Session): Open boto3 session.
        domain (str): VPC such as integration.boss.
        coordinate_frame: Identifies coordinate frame.

    Returns:
        (str): Lookup key.
    """

    query = "SELECT id FROM coordinate_frame WHERE name = %s"

    logging.info('Tunneling to DB (slow) . . .')
    with boss_rds.connect_rds(session, domain) as sql:
        try:
            cursor = sql.cursor()
            cursor.execute(query, (coordinate_frame,))
            coordinate_set = cursor.fetchall()
            if len(coordinate_set) != 1:
                raise ResourceNotFoundException(
                    "Can't find coordinate frame: {}".format(coordinate_frame))
            else:
                logging.info("{} coordinate frame id: {}".format(coordinate_frame, coordinate_set[0][0]))

        finally:
            cursor.close()
    
    return coordinate_set[0][0]

COMMANDS = {
    "sql-list": sql_list,
    "sql-resource-lookup": sql_resource_lookup_key,
    "sql-coord-frame-lookup": sql_coordinate_frame_lookup_key,
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
    



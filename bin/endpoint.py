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

"""A script for manipulating the endpoint instance.

COMMANDS : A dictionary of available commands and the functions to call
"""

import alter_path
import argparse
import boto3
from collections import namedtuple
import json
from lib import aws
from lib.external import ExternalCalls
from lib.hosts import PROD_ACCOUNT, DEV_ACCOUNT
from lib.names import AWSNames
from mysql import connector
import os

DB_HOST_NAME = 'endpoint-db'

class ResourceNotFoundException(Exception):
    """
    Raised when unable to locate the id of collection, experiment, or 
    resource.
    """

"""
Container for MySQL connection parameters.

Fields:
    host (str): DB host name or ip address.
    port (str|int): Port to connect to.
    db (str): Name of DB.
    user (str): DB user name.
    password (str): User password.
"""
DbParams = namedtuple('DbParams', ['host', 'port', 'db', 'user', 'password'])

"""
Container that identifies Boss channel.

Fields:
    collection (str): Collection name.
    experiment (str): Experiment name.
    channel (str): Channel name.
"""
ChannelParams = namedtuple(
    'ChannelParams', ['collection', 'experiment', 'channel'])

def get_mysql_params(session, domain):
    """
    Get MySQL connection info from Vault.

    Args:
        session (Session): Open boto3 session.
        domain (str): VPC such as integration.boss.

    Returns:
        (DbParams): Connection info from Vault.
    """
    keypair = aws.keypair_lookup(session)
    call = ExternalCalls(session, keypair, domain)
    names = AWSNames(domain)

    names = AWSNames(domain)
    print('Getting MySQL parameters from Vault (slow) . . .')
    with call.vault() as vault:
        params = vault.read('secret/endpoint/django/db')

    return DbParams('{}.{}'.format(DB_HOST_NAME, domain),params['port'],params['name'], params['user'], params['password'])

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
    mysql_params = get_mysql_params(session, domain)

    keypair = aws.keypair_lookup(session)
    call = ExternalCalls(session, keypair, domain)

    query = "SELECT * FROM {}".format(db_table)

    print('Tunneling to DB (slow) . . .')
    with call.tunnel(mysql_params.host, mysql_params.port, 'rds') as local_port:
        try:
            sql = connector.connect(
                user=mysql_params.user, password=mysql_params.password, 
                port=local_port, database=mysql_params.db
            )
            try:
                cursor = sql.cursor()
                cursor.execute(query)
                ans = cursor.fetchall()
                for i in ans:
                    print(i)
            finally:
                cursor.close()
        finally:
            sql.close()

def sql_resource_lookup_key(session, domain, resource_params):
    """
    Get the lookup key that identifies the resource from the database.

    Args:
        session (Session): Open boto3 session.
        domain (str): VPC such as integration.boss.
        resource_params (ChannelParams): Identifies collection, experiment or channel.

    Returns:
        (str): Lookup key.
    """
    coll, exp, chan = False, False, False
    mysql_params = get_mysql_params(session, domain)
    resource = resource_params.split("/")
    
    if len(resource) == 0:
        raise Exception("Incorrect number of arguments(Make sure the resource provided has at least a collection to lookup)")
    else:
        if len(resource) > 0:
            coll = True
            collection = resource_params.split("/")[0]
        if len(resource) > 1:
            exp = True
            experiment = resource_params.split("/")[1]
        if len(resource) > 2:
            chan = True
            channel = resource_params.split("/")[2]
        elif len(resource) > 3:
            raise Exception("Only provide /coll/exp/chan")

    keypair = aws.keypair_lookup(session)
    call = ExternalCalls(session, keypair, domain)

    coll_query = "SELECT id FROM collection WHERE name = %s"
    exp_query = "SELECT id FROM experiment WHERE name = %s"
    chan_query = "SELECT id FROM channel WHERE name = %s"

    print('Tunneling to DB (slow) . . .')
    with call.tunnel(mysql_params.host, mysql_params.port, 'rds') as local_port:
        try:
            sql = connector.connect(
                user=mysql_params.user, password=mysql_params.password, 
                port=local_port, database=mysql_params.db
            )
            try:
                if coll:
                    cursor = sql.cursor()
                    cursor.execute(coll_query, (collection,))
                    coll_set = cursor.fetchall()
                    if len(coll_set) != 1:
                        raise ResourceNotFoundException(
                            "Can't find collection: {}".format(collection))
                    else:
                        cuboid_str = "{}&".format(coll_set[0][0])
                        print("{} collection id: {}".format(collection, coll_set[0][0]))
                if exp:
                    cursor.execute(exp_query, (experiment,))
                    exp_set = cursor.fetchall()
                    if len(exp_set) != 1:
                        raise ResourceNotFoundException(
                            "Can't find experiment: {}".format(experiment))
                    else:
                        cuboid_str = cuboid_str + "{}&".format(exp_set[0][0])
                        print("{} experiment id: {}".format(experiment, exp_set[0][0]))
                if chan:
                    cursor.execute(chan_query, (channel,))
                    chan_set = cursor.fetchall()
                    if len(chan_set) != 1:
                        raise ResourceNotFoundException(
                            "Can't find channel: {}".format(experiment))
                    else:
                        cuboid_str = cuboid_str + "{}&".format(chan_set[0][0])
                        print("{} channel id: {}".format(channel, chan_set[0][0]))
            finally:
                cursor.close()
        finally:
            sql.close()
    
    print("Cuboid key: {} \n".format(cuboid_str))
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
    mysql_params = get_mysql_params(session, domain)

    keypair = aws.keypair_lookup(session)
    call = ExternalCalls(session, keypair, domain)

    query = "SELECT id FROM coordinate_frame WHERE name = %s"

    print('Tunneling to DB (slow) . . .')
    with call.tunnel(mysql_params.host, mysql_params.port, 'rds') as local_port:
        try:
            sql = connector.connect(
                user=mysql_params.user, password=mysql_params.password, 
                port=local_port, database=mysql_params.db
            )
            try:
                cursor = sql.cursor()
                cursor.execute(query, (coordinate_frame,))
                coordinate_set = cursor.fetchall()
                if len(coordinate_set) != 1:
                    raise ResourceNotFoundException(
                        "Can't find coordinate frame: {}".format(coordinate_frame))
                else:
                    print("{} coordinate frame id: {}".format(coordinate_frame, coordinate_set[0][0]))

            finally:
                cursor.close()
        finally:
            sql.close()
    
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
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    # specify AWS keys, sets up connection to the client.
    session = aws.create_session(args.aws_credentials)

    if args.command in COMMANDS:
        COMMANDS[args.command](session, args.domain, *args.arguments)
    else:
        parser.print_usage()
        sys.exit(1)
    



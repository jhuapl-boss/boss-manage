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

from contextlib import contextmanager
from collections import namedtuple
from mysql import connector
import logging

from lib.external import ExternalCalls
from lib.names import AWSNames
from lib import aws

@contextmanager
def connect_rds(session, domain):
    """
    Context manager with established connection to rds

    Args:
        session (Session): Open boto3 session.
        domain (str): VPC such as integration.boss.

    Returns:
        sql: connection context
    """
    mysql_params = get_mysql_params(session, domain)

    keypair = aws.keypair_lookup(session)
    call = ExternalCalls(session, keypair, domain)

    logging.info('Tunneling to DB (slow) . . .')
    with call.tunnel(mysql_params.host, mysql_params.port, 'rds') as local_port:
        try:
            sql = connector.connect(
                user=mysql_params.user, password=mysql_params.password, 
                port=local_port, database=mysql_params.db
            )
            yield sql
        finally:
            sql.close()

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
    DB_HOST_NAME = names.endpoint_db.split(".")[0]
    logging.debug("DB Hostname is: {}".format(DB_HOST_NAME))

    logging.info('Getting MySQL parameters from Vault (slow) . . .')
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
    query = "SELECT * FROM {}".format(db_table)

    with connect_rds(session, domain) as sql:
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

    with connect_rds(session, domain) as sql:
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

    with connect_rds(session, domain) as sql:
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

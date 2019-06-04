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

import logging

from lib.external import ExternalCalls
from lib import aws

def sql_tables(session, domain):
    """
    List all tables in sql.

    Args:
        session (Session): Open boto3 session.
        domain (str): VPC such as integration.boss.

    Returns:
        tables(list): Lookup key.
    """
    query = "show tables"
    keypair = aws.keypair_lookup(session)
    call = ExternalCalls(session, keypair, domain)
    with call.connect_rds() as cursor:
        cursor.execute(query)
        tables = cursor.fetchall()
        for i in tables:
            logging.info(tables)
        return tables

def sql_list(session, domain, db_table):
    """
    List all the available members of a given sql table.

    Args:
        session (Session): Open boto3 session.
        domain (str): VPC such as integration.boss.
        db_table: Identifies which table members to list.

    Returns:
        ans(list): list of all members of sql table.
    """
    query = "SELECT * FROM {}".format(db_table)
    keypair = aws.keypair_lookup(session)
    call = ExternalCalls(session, keypair, domain)

    with call.connect_rds() as cursor:
        cursor.execute(query)
        ans = cursor.fetchall()
        if len(ans) == 0:
            raise Exception(
                "Can't find table name: {}".format(db_table))
        else:
            for i in ans:
                logging.info(i)
        return ans

def sql_resource_lookup_key(session, domain, resource_params):
    """
    Get the lookup key that identifies the resource from the database.

    Args:
        session (Session): Open boto3 session.
        domain (str): VPC such as integration.boss.
        resource_params (str): Identifies collection, experiment or channel.

    Returns:
        cuboid_str(str): Cuboid lookup key.
    """
    collection, experiment, channel = None, None, None
    resource = resource_params.split("/")

    keypair = aws.keypair_lookup(session)
    call = ExternalCalls(session, keypair, domain)

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

    with call.connect_rds() as cursor:
        if collection is not None:
            cursor.execute(coll_query, (collection,))
            coll_set = cursor.fetchall()
            if len(coll_set) != 1:
                raise Exception(
                    "Can't find collection: {}".format(collection))
            else:
                cuboid_str = "{}&".format(coll_set[0][0])
                logging.info("{} collection id: {}".format(collection, coll_set[0][0]))
        if experiment is not None:
            cursor.execute(exp_query, (experiment,))
            exp_set = cursor.fetchall()
            if len(exp_set) != 1:
                raise Exception(
                    "Can't find experiment: {}".format(experiment))
            else:
                cuboid_str = cuboid_str + "{}&".format(exp_set[0][0])
                logging.info("{} experiment id: {}".format(experiment, exp_set[0][0]))
        if channel is not None:
            cursor.execute(chan_query, (channel,))
            chan_set = cursor.fetchall()
            if len(chan_set) != 1:
                raise Exception(
                    "Can't find channel: {}".format(channel))
            else:
                cuboid_str = cuboid_str + "{}&".format(chan_set[0][0])
                logging.info("{} channel id: {}".format(channel, chan_set[0][0]))
    
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
        coordinate_set(str): Coordinate Frame lookup key.
    """

    query = "SELECT id FROM coordinate_frame WHERE name = %s"
    keypair = aws.keypair_lookup(session)
    call = ExternalCalls(session, keypair, domain)

    with call.connect_rds() as cursor:
        cursor.execute(query, (coordinate_frame,))
        coordinate_set = cursor.fetchall()
        if len(coordinate_set) != 1:
            raise Exception(
                "Can't find coordinate frame: {}".format(coordinate_frame))
        else:
            logging.info("{} coordinate frame id: {}".format(coordinate_frame, coordinate_set[0][0]))
    
    return coordinate_set[0][0]

def sql_channel_job_ids(session, domain, resource):
    """
    Get a list of channel job ids related to a given channel

    Args:
        session (Session): Open boto3 session.
        domain (str): VPC such as integration.boss.
        resource(str): resource
    
    Returns:
        job_ids(list): job_ids and start dates and x,y and z range associated with channel
            format: (id,                      start_date,                     x_start,y_start,z_start,x_stop, y_stop, z_stop)
            ex:     (2933, datetime.datetime(2019, 3, 16, 21, 33, 37, 831357), 32000,  45824,  14880, 213760, 169728, 14912)
    """
    coll = resource.split("/")[0]
    exp = resource.split("/")[1]
    chan = resource.split("/")[2]

    query = "SELECT id,start_date,x_start,y_start,z_start,x_stop,y_stop,z_stop FROM ingest_job WHERE collection = '{}' AND experiment = '{}' AND channel = '{}'".format(coll,exp,chan)
    keypair = aws.keypair_lookup(session)
    call = ExternalCalls(session, keypair, domain)

    with call.connect_rds() as cursor:
        cursor.execute(query)
        job_ids = cursor.fetchall()
        if len(job_ids) == 0:
            raise Exception(
                "Can't find resource name: {}/{}/{}".format(coll,exp,chan))
        else:
            logging.info("Job-Ids corresponding to {}/{}/{} \n".format(coll,exp,chan))
            for i in job_ids:
                logging.info(i)
        return job_ids
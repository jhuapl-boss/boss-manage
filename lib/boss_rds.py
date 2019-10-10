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
LOGGER = logging.getLogger(__name__)

def sql_tables(bosslet_config):
    """
    List all tables in sql.

    Args:
        bosslet_config (BossConfiguration): Bosslet configuration object

    Returns:
        tables(list): Lookup key.
    """
    query = "show tables"
    with bosslet_config.call.connect_rds() as cursor:
        cursor.execute(query)
        tables = cursor.fetchall()
        for i in tables:
            LOGGER.info(tables)
        return tables

def sql_list(bosslet_config, db_table):
    """
    List all the available members of a given sql table.

    Args:
        bosslet_config (BossConfiguration): Bosslet configuration object
        db_table: Identifies which table members to list.

    Returns:
        ans(list): list of all members of sql table.
    """
    query = "SELECT * FROM {}".format(db_table)
    with bosslet_config.call.connect_rds() as cursor:
        cursor.execute(query)
        ans = cursor.fetchall()
        if len(ans) == 0:
            raise Exception(
                "Can't find table name: {}".format(db_table))
        else:
            for i in ans:
                LOGGER.info(i)
        return ans

def sql_resource_lookup_key(bosslet_config, resource_params):
    """
    Get the lookup key that identifies the resource from the database.

    Args:
        bosslet_config (BossConfiguration): Bosslet configuration object
        resource_params (str): Identifies collection, experiment or channel.

    Returns:
        cuboid_str(str): Cuboid lookup key.
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

    with bosslet_config.call.connect_rds() as cursor:
        if collection is not None:
            cursor.execute(coll_query, (collection,))
            coll_set = cursor.fetchall()
            if len(coll_set) != 1: # TODO: Alert the user when there are more than one results
                raise Exception(
                    "Can't find collection: {}".format(collection))
            else:
                cuboid_str = "{}&".format(coll_set[0][0])
                LOGGER.info("{} collection id: {}".format(collection, coll_set[0][0]))
        if experiment is not None:
            cursor.execute(exp_query, (experiment,))
            exp_set = cursor.fetchall()
            if len(exp_set) != 1: # TODO: Alert the user when there are more than one results
                raise Exception(
                    "Can't find experiment: {}".format(experiment))
            else:
                cuboid_str = cuboid_str + "{}&".format(exp_set[0][0])
                LOGGER.info("{} experiment id: {}".format(experiment, exp_set[0][0]))
        if channel is not None:
            cursor.execute(chan_query, (channel,))
            chan_set = cursor.fetchall()
            if len(chan_set) != 1: # TODO: Alert the user when there are more than one results
                raise Exception(
                    "Can't find channel: {}".format(channel))
            else:
                cuboid_str = cuboid_str + "{}&".format(chan_set[0][0])
                LOGGER.info("{} channel id: {}".format(channel, chan_set[0][0]))
    
    LOGGER.info("Cuboid key: {} \n".format(cuboid_str))
    return cuboid_str

def sql_coordinate_frame_lookup_key(bosslet_config, coordinate_frame):
    """
    Get the lookup key that identifies the coordinate fram specified.

    Args:
        bosslet_config (BossConfiguration): Bosslet configuration object
        coordinate_frame: Identifies coordinate frame.

    Returns:
        coordinate_set(str): Coordinate Frame lookup key.
    """

    query = "SELECT id FROM coordinate_frame WHERE name = %s"
    with bosslet_config.call.connect_rds() as cursor:
        cursor.execute(query, (coordinate_frame,))
        coordinate_set = cursor.fetchall()
        if len(coordinate_set) != 1:
            raise Exception(
                "Can't find coordinate frame: {}".format(coordinate_frame))
        else:
            LOGGER.info("{} coordinate frame id: {}".format(coordinate_frame, coordinate_set[0][0]))
    
    return coordinate_set[0][0]

def sql_channel_job_ids(bosslet_config, resource):
    """
    Get a list of channel job ids related to a given channel

    Args:
        bosslet_config (BossConfiguration): Bosslet configuration object
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
    with bosslet_config.call.connect_rds() as cursor:
        cursor.execute(query)
        job_ids = cursor.fetchall()
        if len(job_ids) == 0:
            raise Exception(
                "Can't find resource name: {}/{}/{}".format(coll,exp,chan))
        else:
            LOGGER.info("\n Job-Ids corresponding to {}/{}/{}".format(coll,exp,chan))
            LOGGER.info("< id,                      start_date,                     x_start,y_start,z_start,x_stop, y_stop, z_stop>")
            for i in job_ids:
                LOGGER.info(i)
        return job_ids

def sql_get_names_from_lookup_keys(bosslet_config, lookup_keys):
    """
    Gets collection/experiment/channel names from lookup keys.

    Args:
        bosslet_config (BossConfiguration): Bosslet configuration object
        lookup_keys (list[str]): List of lookup keys to get col/exp/chan names for.
                                 Expected format f'{col_id}&{exp_id}&{chan_id}'

    Returns:
        (list[tuple(str, str, str)]): List of tuples of collection/exp/chan names.
                                      If a look up key is not found, empty strings
                                      will be returned for that key's corresponding tuple.
    """
    names = []
    if len(lookup_keys) < 1:
        LOGGER.error('No lookup keys provided, aborting.')
        return names

    query = 'SELECT collection_name, experiment_name, channel_name FROM lookup WHERE lookup_key = %(key)s'
    with bosslet_config.call.connect_rds() as cursor:
        for key in lookup_keys:
            cursor.execute(query, { 'key': key })
            rows = cursor.fetchall()
            if(len(rows) > 0):
                this_row = (rows[0][0], rows[0][1], rows[0][2])
            else:
                this_row = ('', '', '')
            names.append(this_row)
            LOGGER.info('key: {}, coll: {}, exp: {}, chan: {}'.format(key, this_row[0], this_row[1], this_row[2]))
        
    return names

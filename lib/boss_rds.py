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
    DB_HOST_NAME = names.endpoint_db.split(".")[0]
    logging.debug("DB Hostname is: {}".format(DB_HOST_NAME))

    logging.info('Getting MySQL parameters from Vault (slow) . . .')
    with call.vault() as vault:
        params = vault.read('secret/endpoint/django/db')

    return DbParams('{}.{}'.format(DB_HOST_NAME, domain),params['port'],params['name'], params['user'], params['password'])

@contextmanager
def connect_rds(session, domain):
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
    
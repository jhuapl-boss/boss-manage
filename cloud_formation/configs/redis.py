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

"""
Create the redis configuration which consists of
  * redis cluster for cache
  * redis cluster for cache-state

The redis configuration creates cache and cache-state redis clusters for the
BOSS system. redis configuration is in a separate file to improve the update process
The redis configuration expects to be launched / created
in a VPC created by the core configuration. It also expects for the user to
select the same KeyPair used when creating the core configuration.
"""

from lib.cloudformation import CloudFormationConfiguration, Arg, Ref, Arn
from lib.names import AWSNames
from lib import aws
from lib import constants as const
from lib.cloudformation import get_scenario


def create_config(session, domain, keypair=None):
    """
    Create the CloudFormationConfiguration object.
    Args:
        session: amazon session object
        domain (string): domain of the stack being created
        keypair: keypair used to by instances being created

    Returns: the config for the Cloud Formation stack

    """

    names = AWSNames(domain)

    config = CloudFormationConfiguration('redis', domain, const.REGION)

    vpc_id = config.find_vpc(session)
    az_subnets, external_subnets = config.find_all_availability_zones(session)
    sgs = aws.sg_lookup_all(session, vpc_id)

    # Create the Cache and CacheState Redis Clusters
    REDIS_PARAMETERS = {
        "maxmemory-policy": "volatile-lru",
        "reserved-memory": str(get_scenario(const.REDIS_RESERVED_MEMORY, 0) * 1000000),
        "maxmemory-samples": "5", # ~ 5 - 10
    }

    config.add_redis_replication("Cache",
                                 names.cache,
                                 az_subnets,
                                 [sgs[names.internal]],
                                 type_=const.REDIS_CACHE_TYPE,
                                 version="3.2.4",
                                 clusters=const.REDIS_CLUSTER_SIZE,
                                 parameters=REDIS_PARAMETERS)

    config.add_redis_replication("CacheState",
                                 names.cache_state,
                                 az_subnets,
                                 [sgs[names.internal]],
                                 type_=const.REDIS_TYPE,
                                 version="3.2.4",
                                 clusters=const.REDIS_CLUSTER_SIZE)

    # This one may not be created depending on the scenario type.
    if get_scenario(const.REDIS_SESSION_TYPE, None) is not None:
        config.add_redis_replication("CacheSession",
                                     names.cache_session,
                                     az_subnets,
                                     [sgs[names.internal]],
                                     type_=const.REDIS_SESSION_TYPE,
                                     version="3.2.4",
                                     clusters=1)

    return config


def generate(session, domain):
    """Create the configuration and save it to disk"""
    keypair = aws.keypair_lookup(session)

    config = create_config(session, domain, keypair)
    config.generate()


def create(session, domain):
    """
    Create the configuration and launches it
    Args:
        session(Session): information for performing lookups 
        domain(str): internal DNS name

    Returns:
        None
    """
    config = create_config(session, domain)

    success = config.create(session)

    if not success:
        raise Exception("Create Failed")
    else:
        post_init(session, domain)


def post_init(session, domain):
    print("post_init")


def update(session, domain):
    keypair = aws.keypair_lookup(session)
    names = AWSNames(domain)

    config = create_config(session, domain, keypair)
    success = config.update(session)

    return success


def delete(session, domain):
    names = AWSNames(domain)
    CloudFormationConfiguration('redis', domain).delete(session)

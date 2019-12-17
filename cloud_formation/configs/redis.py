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

DEPENDENCIES = ['core']

"""
Create the redis configuration which consists of
  * redis cluster for cache
  * redis cluster for cache-state
  # redis cluster for cache-throttle
  * redis for session key 

The redis configuration creates cache and cache-state redis clusters for the
BOSS system. redis configuration is in a separate file to improve the update process
"""

from lib.cloudformation import CloudFormationConfiguration, Arg, Ref, Arn
from lib import aws
from lib import constants as const


def create_config(bosslet_config):
    names = bosslet_config.names
    session = bosslet_config.session

    config = CloudFormationConfiguration('redis', bosslet_config)

    vpc_id = config.find_vpc()
    internal_subnets, external_subnets = config.find_all_subnets()
    sgs = aws.sg_lookup_all(session, vpc_id)

    # Create the Cache and CacheState Redis Clusters
    REDIS_PARAMETERS = {
        "maxmemory-policy": "volatile-lru",
        "reserved-memory-percent": str(const.REDIS_RESERVED_MEMORY_PERCENT),
        "maxmemory-samples": "5", # ~ 5 - 10
    }

    config.add_redis_replication("Cache",
                                 names.cache.redis,
                                 internal_subnets,
                                 [sgs[names.internal.sg]],
                                 type_=const.REDIS_CACHE_TYPE,
                                 version="3.2.4",
                                 clusters=const.REDIS_CLUSTER_SIZE,
                                 parameters=REDIS_PARAMETERS)

    config.add_redis_replication("CacheState",
                                 names.cache_state.redis,
                                 internal_subnets,
                                 [sgs[names.internal.sg]],
                                 type_=const.REDIS_TYPE,
                                 version="3.2.4",
                                 clusters=const.REDIS_CLUSTER_SIZE)

    # This one may not be created depending on the scenario type.
    if const.REDIS_SESSION_TYPE is not None:
        config.add_redis_replication("CacheSession",
                                     names.cache_session.redis,
                                     internal_subnets,
                                     [sgs[names.internal.sg]],
                                     type_=const.REDIS_SESSION_TYPE,
                                     version="3.2.4",
                                     clusters=1)

    if const.REDIS_THROTTLE_TYPE is not None:
        config.add_redis_replication("CacheThrottle",
                                     names.cache_throttle.redis,
                                     internal_subnets,
                                     [sgs[names.internal.sg]],
                                     type_=const.REDIS_THROTTLE_TYPE,
                                     version="3.2.4",
                                     clusters=1)

    return config


def generate(bosslet_config):
    """Create the configuration and save it to disk"""
    config = create_config(bosslet_config)
    config.generate()


def create(bosslet_config):
    config = create_config(bosslet_config)
    config.create()

def update(bosslet_config):
    config = create_config(bosslet_config)
    config.update()


def delete(bosslet_config):
    config = CloudFormationConfiguration('redis', bosslet_config)
    config.delete()

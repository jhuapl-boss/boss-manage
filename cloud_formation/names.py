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
This is a set of functions to ensure the same name is used for a resource
across multiple files/configurations.
"""

CACHE_MANAGER = 'cachemanager'
CACHE_DB = 'cachedb'
CUBOID_BUCKET = 'cuboids'
MULTI_LAMBDA = 'multiLambda'
S3_INDEX = 's3index'
TILE_BUCKET = 'tiles'
TILE_INDEX = 'tileindex'

def get_cache_manager(domain):
    """Get the domain name of the cache manager.

    Returns:
        (string)
    """
    return CACHE_MANAGER + '.' + domain

def get_cache_db(domain):
    """Get the domain name of the cache database.

    Returns:
        (string)
    """
    return CACHE_DB + '.' + domain

def get_cuboid_bucket(domain):
    """Get the domain name of the cuboid bucket.

    Returns:
        (string)
    """
    return CUBOID_BUCKET + '.' + domain

def get_multi_lambda(domain):
    """Get the domain name of the lambda function.

    Returns:
        (string)
    """
    return MULTI_LAMBDA + '.' + domain

def get_s3_index(domain):
    """Get the domain name of the S3 index table in DynamoDB.

    Returns:
        (string)
    """
    return S3_INDEX + '.' + domain

def get_tile_bucket(domain):
    """Get the domain name of the S3 tile bucket.

    Returns:
        (string)
    """
    return TILE_BUCKET + '.' + domain

def get_tile_index(domain):
    """Get the domain name of the tile index table in DynamoDB.

    Returns:
        (string)
    """
    return TILE_INDEX + '.' + domain

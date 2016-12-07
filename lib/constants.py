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

import os

# Region api is created in.  Later versions of boto3 should allow us to
# extract this from the session variable.  Hard coding for now.
REGION = 'us-east-1'
INCOMING_SUBNET = "52.3.13.189/32"  # microns-bastion elastic IP

cur_dir = os.path.dirname(os.path.realpath(__file__))
REPO_ROOT = os.path.realpath(os.path.join(cur_dir, '..'))


########################
# Lambda Files
LAMBDA_DIR = os.path.join(REPO_ROOT, 'cloud_formation', 'lambda')
DNS_LAMBDA = LAMBDA_DIR + '/updateRoute53/index.py'


########################
# DynamoDB Table Schemas
SALT_DIR = os.path.join(REPO_ROOT, 'salt_stack', 'salt')

DYNAMO_METADATA_SCHEMA = SALT_DIR + '/boss/files/boss.git/django/bosscore/dynamo_schema.json'
DYNAMO_S3_INDEX_SCHEMA = SALT_DIR + '/spdb/files/spdb.git/spatialdb/dynamo/s3_index_table.json'
DYNAMO_TILE_INDEX_SCHEMA  = SALT_DIR + '/ndingest/files/ndingest.git/nddynamo/schemas/boss_tile_index.json'
# Annotation id to supercuboid table.
DYNAMO_ID_INDEX_SCHEMA = SALT_DIR + '/spdb/files/spdb.git/spatialdb/dynamo/id_index_schema.json'
# Annotation id count table (allows for reserving the next id in a channel).
DYNAMO_ID_COUNT_SCHEMA = SALT_DIR + '/spdb/files/spdb.git/spatialdb/dynamo/id_count_schema.json'


########################
# Other Salt Files
KEYCLOAK_REALM = SALT_DIR + '/keycloak/files/BOSS.realm'


########################
# Vault Secret Paths
VAULT_AUTH = "secret/auth"
VAULT_REALM = "secret/auth/realm"
VAULT_KEYCLOAK = "secret/keycloak"
VAULT_ENDPOINT = "secret/endpoint/django"
VAULT_ENDPOINT_DB = "secret/endpoint/django/db"
VAULT_ENDPOINT_AUTH = "secret/endpoint/auth"


########################
# Service Check Timeouts
TIMEOUT_VAULT = 120
TIMEOUT_KEYCLOAK = 120


########################
# Machine Instance Types
ENDPOINT_TYPE = {
    "development": "t2.small",
    "production": "m4.large",
}

RDS_TYPE = {
    "development": "db.t2.micro",
    "production": "db.t2.medium",
}

REDIS_TYPE = {
    "development": "cache.t2.small",
    "production": "cache.m3.xlarge",
}


########################
# Machine Cluster Sizes
AUTH_CLUSTER_SIZE = { # Auth Server Cluster is a fixed size
    "development" : 1,
    "production": 3 # should be an odd number
}

CONSUL_CLUSTER_SIZE = { # Consul Cluster is a fixed size
    "development" : 1,
    "production": 5 # can tolerate 2 failures
}

VAULT_CLUSTER_SIZE = { # Vault Cluster is a fixed size
    "development" : 1,
    "production": 3 # should be an odd number
}

ENDPOINT_CLUSTER_SIZE = {
    "development": 1,
    "production": 1,
}

REDIS_CLUSTER_SIZE = {
    "development": 1,
    "production": 2,
}


########################
# Machine Configurations
ENDPOINT_DB_CONFIG = {
    "name":"boss",
    "user":"testuser", # DP ???: Why is the name testuser? should we generate the username too?
    "password": "",
    "port": "3306"
}

BASTION_AMI = "amzn-ami-vpc-nat-hvm-2015.03.0.x86_64-ebs"
# Configure Squid to allow clustered Vault access, restricted to connections from the Bastion
BASTION_USER_DATA = """#cloud-config
packages:
    - squid

write_files:
    - content: |
            acl localhost src 127.0.0.1/32 ::1
            acl to_localhost dst 127.0.0.0/8 0.0.0.0/32 ::1
            acl localnet dst 10.0.0.0/8
            acl Safe_ports port 8200

            http_access deny !Safe_ports
            http_access deny !localnet
            http_access deny to_localhost
            http_access allow localhost
            http_access deny all

            http_port 3128
      path: /etc/squid/squid.conf
      owner: root squid
      permissions: '0644'

runcmd:
    - chkconfig squid on
    - service squid start
"""

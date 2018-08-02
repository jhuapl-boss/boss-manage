# Copyright 2018 The Johns Hopkins University Applied Physics Laboratory
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
import sys
import yaml

PRODUCTION_MAILING_LIST = "ProductionMicronsMailingList"
PRODUCTION_BILLING_TOPIC = "ProductionBillingList"
MAX_ALARM_DOLLAR = 200  # Maximum size of alarms in $1,000s


##################
# Scenario Support
def load_scenario(scenario):
    # Locate the imported module so code can reference global
    # variables without using the 'global' keyword
    d = sys.modules['lib.constants'].__dict__

    if scenario is not None:
        file = "{}.yml".format(scenario)
        path = repo_path("cloud_formation", "scenarios", file)

        if not os.path.exists(path):
            print("Scenario file '{}' doesn't exist".format(path))
            return

        try:
            with open(path, 'r') as fh:
                config = yaml.load(fh.read())
        except Exception as ex:
            print("Problem loading scenario file")
            print(ex)

        for key in config:
            d[key] = config[key]


########################
# Path functions
def find_dir(dir_):
    return os.path.dirname(os.path.realpath(dir_))

def path(*args):
    return os.path.realpath(os.path.join(*args))

cur_dir = find_dir(__file__)
REPO_ROOT = path(cur_dir, '..')

def repo_path(*args):
    return path(REPO_ROOT, *args)


LAMBDA_SUBNETS = 16

########################
# Lambda Files
LAMBDA_DIR = repo_path('cloud_formation', 'lambda')
DNS_LAMBDA = LAMBDA_DIR + '/updateRoute53/index.py'
VAULT_LAMBDA = LAMBDA_DIR + '/monitors/chk_vault.py'
CONSUL_LAMBDA = LAMBDA_DIR + '/monitors/chk_consul.py'
INGEST_LAMBDA = LAMBDA_DIR + '/ingest_populate/ingest_queue_upload.py'
DOWNSAMPLE_DLQ_LAMBDA = LAMBDA_DIR + '/downsample/dlq.py'


########################
# DynamoDB Table Schemas
SALT_DIR = repo_path('salt_stack', 'salt')

DYNAMO_METADATA_SCHEMA = SALT_DIR + '/boss/files/boss.git/django/bosscore/dynamo_schema.json'
DYNAMO_S3_INDEX_SCHEMA = SALT_DIR + '/spdb/files/spdb.git/spatialdb/dynamo/s3_index_table.json'
DYNAMO_TILE_INDEX_SCHEMA  = SALT_DIR + '/ndingest/files/ndingest.git/nddynamo/schemas/boss_tile_index.json'
# Max number to append to task id attribute of tile index (used to prevent hot
# partitions when writing to the task_id_index GSI).
MAX_TASK_ID_SUFFIX = 100
# Annotation id to supercuboid table.
DYNAMO_ID_INDEX_SCHEMA = SALT_DIR + '/spdb/files/spdb.git/spatialdb/dynamo/id_index_schema.json'
# Annotation id count table (allows for reserving the next id in a channel).
DYNAMO_ID_COUNT_SCHEMA = SALT_DIR + '/spdb/files/spdb.git/spatialdb/dynamo/id_count_schema.json'

# Threshold when a new chunk should be added to the partition key of the id
# index.  If the consumed write capacity is >= this number, write new
# morton ids to a new key.
DYNAMO_ID_INDEX_NEW_CHUNK_THRESHOLD = 100

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
VAULT_PROOFREAD = "secret/proofreader/django"
VAULT_PROOFREAD_DB = "secret/proofreader/django/db"
VAULT_PROOFREAD_AUTH = "secret/proofreader/auth"


########################
# Service Check Timeouts
TIMEOUT_VAULT = 120
TIMEOUT_KEYCLOAK = 150


########################
# Machine Instance Types
ENDPOINT_TYPE = "t2.micro"
RDS_TYPE = "db.t2.micro"
REDIS_CACHE_TYPE = "cache.t2.micro"
REDIS_TYPE = "cache.t2.micro"
CACHE_MANAGER_TYPE = "t2.micro"
ACTIVITIES_TYPE = "t2.micro"


########################
# Machine Cluster Sizes
AUTH_CLUSTER_SIZE = 1
CONSUL_CLUSTER_SIZE = 1
VAULT_CLUSTER_SIZE = 1
ENDPOINT_CLUSTER_MIN = 1
ENDPOINT_CLUSTER_MAX = 1
REDIS_CLUSTER_SIZE = 1


#################
# Resource Memory
REDIS_RESERVED_MEMORY = 0


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
            acl localnet dst {}
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

# Copyright 2014 The Johns Hopkins University Applied Physics Laboratory
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

from . import hosts

def format_capitalize(fqdn):
    return "".join([x.capitalize() for x in fqdn.split('.')])

def format_dash(fqdn):
    return fqdn.replace('.', '-')

class AWSNameAccumulator(object):
    def __init__(self, initial_value, callback):
        self.acc = [initial_value]
        self.cb = callback

    def __getattr__(self, key):
        self.acc.append(key)

        if len(self.acc) == 2:
            return self.cb(*self.acc)
        else:
            return self

    def __getitem__(self, key):
        return self.__getattr__(key)

class AWSNames(object):
    def __init__(self, bosslet_config):
        self.bosslet_config = bosslet_config

    def public_dns(self, name):
        try:
            name = self.bosslet_config.EXTERNAL_FORMAT.format(machine = name)
        except:
            pass

        return name + '.' + self.bosslet_config.EXTERNAL_DOMAIN

    def __getattr__(self, key):
        return AWSNameAccumulator(key, self.build)

    def __getitem__(self, key): # For dynamically building names from input
        return self.__getattr__(key)

    TYPES = {
        'stack': format_capitalize,
        'subnet': None,
        'dns': None, # Internal DNS name
        'lambda_': None, # Need '_' as lambda is a keyword
        'sns': None,
        'sg': None, # Security Group
        'rt': None, # Route Table
        'gw': None, # Gateway
        'ami': None,
    }

    RESOURCES = {
        'core': 'core',
        'internal': 'internal',
        'external': 'external',
        'bastion': 'bastion',
        'consul': 'consul',
        'vault': 'vault',
        'auth': 'auth',
        'auth_db': 'auth-db',
        'dns': 'dns',
        'ssh': 'ssh',
        'internet': 'internet',
    }

    def build(self, resource_type, name):
        if resource_type not in self.TYPES:
            raise AttributeError("'{}' is not a valide resource type".format(resource_type))

        if name not in self.RESOURCES:
            raise AttributeError("'{}' is not a valid resource name".format(name))

        if resource_type == 'ami':
            suffix = self.bosslet_config.AMI_SUFFIX
            return self.RESOURCES[name] + suffix

        domain = self.bosslet_config.INTERNAL_DOMAIN
        fqdn = self.RESOURCES[name] + '.' + domain

        transform = self.TYPES[resource_type]
        if transform:
            fqdn = transform(fqdn)

        return fqdn



'''
class AWSNames(object):
    """
    All names are returned as dotted names (containg '.' between each component).
    Some AWS resources cannot have '.' in their name. In these cases the
    CloudFormationConfiguration add_* methods will convert '.' to '-' as needed.
    """

    def __init__(self, base):
        self.base = base
        self.base_dot = '.' + base

    ##################################
    # Generic rules for different type of AWS resources
    def subnet(self, name):
        return name + self.base_dot

    def public_dns(self, name):
        name = name.split('.')[0]
        if self.base in hosts.BASE_DOMAIN_CERTS.keys():
            dns = name + "." + hosts.BASE_DOMAIN_CERTS[self.base]
        else:
            stack = self.base.split('.')[0]
            dns = "{}-{}.{}".format(name, stack, hosts.DEV_DOMAIN)
        return dns

    ##################################
    # Properties for common / well known BOSS resources
    RESOURCES = {
        "bastion": "bastion",
        "auth": "auth", # ec2 instance, security group
        "auth_db": "auth-db",
        "vault": "vault",
        "consul": "consul",
        "api": "api", # public name of endoint
        "endpoint": "endpoint",
        "endpoint_db": "endpoint-db",
        "endpoint_elb": "elb",
        "proofreader": "proofreader-web",
        "proofreader_db": "proofreader-db",
        "dns": "dns", # lambda, sns topic display name, sns topic name
        "internal": "internal", # subnet, security group, route table
        "ssh": "ssh",
        "https": "https",
        "http": "http",
        "internet": "internet",
        "meta": "bossmeta",
        "cache": "cache",
        "cache_state": "cache-state",
        "cache_manager": "cachemanager",
        "cache_db": "cachedb",
        "cuboid_bucket": "cuboids",
        "multi_lambda": "multiLambda",
        "s3_index": "s3index",
        "ingest_bucket": "ingest",
        "tile_bucket": "tiles",
        "tile_index": "tileindex",
        "id_index": "idIndex",
        "id_count_index": "idCount",
        "s3flush_queue": "S3flush",
        "deadletter_queue": "Deadletter",
        'write_lock_topic': 'WriteLockAlert',
        'write_lock': 'WriteLockAlert',
        'vault_monitor': 'vaultMonitor',
        'consul_monitor': 'consulMonitor',
        'vault_consul_check': 'checkVaultConsul',
        'activities': 'activities',
        'delete_cuboid': 'Delete.Cuboid',
        'delete_bucket': 'delete',
        'delete_experiment': 'Delete.Experiment',
        'delete_collection': 'Delete.Collection',
        'delete_coord_frame': 'Delete.CoordFrame',
        'query_deletes': 'Query.Deletes',
        'delete_event_rule': 'deleteEventRule',
        'delete_lambda': "deleteLambda",
        'resolution_hierarchy': 'Resolution.Hierarchy',
        'downsample_volume': 'Downsample.Volume',
        'ingest_queue_populate': 'Ingest.Populate',
        'ingest_queue_upload': 'Ingest.Upload',
        'ingest_lambda': 'IngestUpload',
        'dynamo_lambda': 'dynamoLambda',
        'trigger_dynamo_autoscale': 'triggerDynamoAutoscale'
    }

    def __getattr__(self, name):
        if name not in self.RESOURCES:
            raise AttributeError("{} is not a valid BOSS AWS Resource name".format(name))

        hostname = self.RESOURCES[name]
        if name in ['write_lock_topic']:
            return hostname

        fq_hostname = hostname + self.base_dot

        if name in ['multi_lambda', 'write_lock', 'vault_monitor', 'consul_monitor', 'vault_consul_check',
                    'delete_lambda', 'ingest_lambda', 'dynamo_lambda']:
            fq_hostname = fq_hostname.replace('.','-')

        if name in ['s3flush_queue', 'deadletter_queue', 'delete_cuboid', 'query_deletes',
                    'ingest_queue_populate', 'ingest_queue_upload', 'resolution_hierarchy',
                    'downsample_volume', 'delete_experiment', 'delete_collection', 'delete_coord_frame']:
            fq_hostname = "".join(map(lambda x: x.capitalize(), fq_hostname.split('.')))

        return fq_hostname
'''

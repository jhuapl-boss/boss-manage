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
        name = self.bosslet_config.EXTERNAL_FORMAT.format(machine = name)

        return name + '.' + self.bosslet_config.EXTERNAL_DOMAIN

    def __getattr__(self, key):
        return AWSNameAccumulator(key, self.build)

    def __getitem__(self, key): # For dynamically building names from input
        return self.__getattr__(key)

    TYPES = {
        'stack': format_capitalize,
        'subnet': None,
        'dns': None, # Internal DNS name, EC2 and ELB
                     # XXX: maybe ec2, as it is an EC2 instance name
        'lambda_': format_dash, # Need '_' as lambda is a keyword
                                 # XXX: not all lambdas used dashes
        'rds': None,
        'sns': None,
        'sqs': format_capitalize,
        'sg': None, # Security Group
        'rt': None, # Route Table
        'gw': None, # Gateway
        'ami': None,
        'redis': None, # ElastiSearch Redis
        'ddb': None, # DynamoDB
        's3': None, # S3 Bucket
        'sfn': format_capitalize, # StepFunction
        'cw': format_dash, # CloudWatch Rule

        'zip': lambda x: x.lower() + '.zip', # lambda code files
    }

    RESOURCES = {
        # Ordered by name to make it easy to find an entry
        'activities': 'activities',
        'auth': 'auth',
        'auth_db': 'auth-db',
        'bastion': 'bastion',
        'cache': 'cache', # Redis server to cache cuboids
        'cache_manager': 'cachemanager',
        'cache_session': 'cache-session', # Redis server for Django sessions
        'cache_state': 'cache-state',
        'consul': 'consul',
        'consul_monitor': 'consulMonitor',
        'copy_cuboid_dlq': 'copyCuboidDlq',
        'copy_cuboid_lambda': 'copyCuboidLambda',
        'core': 'core',
        'cuboid_bucket': 'cuboids',
        "cuboid_ids_bucket": "cuboid-ids",
        'deadletter': 'Deadletter',
        'default': 'default',
        'delete_bucket': 'delete',
        'delete_collection': 'Delete.Collection',
        'delete_coord_frame': 'Delete.CoordFrame',
        'delete_cuboid': 'Delete.Cuboid',
        'delete_event_rule': 'deleteEventRule',
        'delete_experiment': 'Delete.Experiment',
        'delete_tile_index_entry': 'deleteTileEntryLambda',
        'delete_tile_objs': 'deleteTileObjsLambda',
        'dns': 'dns',
        'downsample_dlq': 'downsample-dlq',
        'downsample_volume': 'downsample.volume',
        'dynamodb_autoscale': 'dynamodb_autoscale',
        'dynamo_lambda': 'dynamoLambda',
        'endpoint_db': 'endpoint-db',
        'endpoint_elb': 'elb',
        'endpoint': 'endpoint',
        'external': 'external',
        'https': 'https',
        'id_count_index': 'idCount',
        'id_index': 'idIndex',
        'index_batch_enqueue_cuboids': 'indexBatchEnqueueCuboidsLambda',
        'index_check_for_throttling': 'indexCheckForThrottlingLambda',
        'index_cuboids_keys': 'cuboidsKeys',
        'index_cuboid_supervisor': 'Index.CuboidSupervisor',
        'index_deadletter': 'indexDeadLetter',
        'index_dequeue_cuboid_keys': 'indexDequeueCuboidsLambda',
        'index_dequeue_cuboids': 'Index.DequeueCuboids',
        'index_enqueue_cuboids': 'Index.EnqueueCuboids',
        'index_fanout_dequeue_cuboid_keys': 'indexFanoutDequeueCuboidsKeysLambda',
        'index_fanout_dequeue_cuboids': 'Index.FanoutDequeueCuboids',
        'index_fanout_enqueue_cuboid_keys': 'indexFanoutEnqueueCuboidsKeysLambda',
        'index_fanout_enqueue_cuboids': 'Index.FanoutEnqueueCuboids',
        'index_fanout_id_writer': 'indexFanoutIdWriterLambda',
        'index_fanout_id_writers': 'Index.FanoutIdWriters',
        'index_find_cuboids': 'indexFindCuboidsLambda',
        'index_get_num_cuboid_keys_msgs': 'indexGetNumCuboidKeysMsgsLambda',
        'index_id_writer': 'Index.IdWriter',
        'index_invoke_index_supervisor': 'indexInvokeIndexSupervisorLambda',
        'index_load_ids_from_s3': 'indexLoadIdsFromS3Lambda',
        'index_s3_writer': 'indexS3WriterLambda',
        'index_split_cuboids': 'indexSplitCuboidsLambda',
        'index_supervisor': 'Index.Supervisor',
        'index_write_failed': 'indexWriteFailedLambda',
        'index_write_id': 'indexWriteIdLambda',
        'ingest_bucket': 'ingest',
        'ingest_cleanup_dlq': 'IngestCleanupDlq',
        'ingest_lambda': 'IngestUpload',
        'ingest_queue_populate': 'Ingest.Populate',
        'ingest_queue_upload': 'Ingest.Upload',
        'internal': 'internal',
        'internet': 'internet',
        'meta': 'bossmeta',
        'multi_lambda': 'multiLambda',
        'query_deletes': 'Query.Deletes',
        'resolution_hierarchy': 'Resolution.Hierarchy',
        's3flush': 'S3flush',
        's3_index': 's3index',
        'ssh': 'ssh',
        'start_sfn': 'startSfnLambda',
        'tile_bucket': 'tiles',
        'tile_index': 'tileindex',
        'tile_ingest': 'tileIngestLambda',
        'tile_uploaded': 'tileUploadLambda',
        'trigger_dynamo_autoscale': 'triggerDynamoAutoscale',
        'vault_consul_check': 'checkVaultConsul',
        'vault_monitor': 'vaultMonitor',
        'vault': 'vault',
    }

    def build(self, resource_type, name):
        if resource_type not in self.TYPES:
            raise AttributeError("'{}' is not a valide resource type".format(resource_type))

        if name not in self.RESOURCES:
            raise AttributeError("'{}' is not a valid resource name".format(name))

        if self.TYPES[resource_type] is False:
            return self.RESOURCES[name]
        elif resource_type == 'ami':
            suffix = self.bosslet_config.AMI_SUFFIX
            return self.RESOURCES[name] + suffix
        else:
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

    @classmethod
    def create_from_lambda_name(cls, name):
        """
        Instantiate AWSNames from the name of a lambda function.  Used by
        lambdas so they can look up names of other resources.

        Args:
            name (str): Name of lambda function (ex: multiLambda-integration-boss)

        Returns:
            (AWSNames)

        """
        # Lambdas names can't have periods; restore proper name.
        dotted_name = name.replace('-', '.')
        domain = dotted_name.split('.', 1)[1]
        return cls(domain)

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
        'cache_session': 'cache-session',   # Redis server for Django sessions.
        "cache": "cache",                   # Redis server to cache cuboids.
        "cache_state": "cache-state",
        "cache_manager": "cachemanager",
        "cache_db": "cachedb",
        "cuboid_bucket": "cuboids",
        "multi_lambda": "multiLambda",
        "s3_index": "s3index",
        "ingest_bucket": "ingest",
        "tile_bucket": "tiles",
        "delete_tile_objs_lambda": 'deleteTileObjsLambda',
        "tile_index": "tileindex",
        "cuboid_ids_bucket": "cuboid-ids",
        "delete_tile_index_entry_lambda": 'deleteTileEntryLambda',
        "ingest_cleanup_dlq": "IngestCleanupDlq",
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
        'downsample_volume_lambda': 'downsampleVolumeLambda',
        'ingest_queue_populate': 'Ingest.Populate',
        'ingest_queue_upload': 'Ingest.Upload',
        'ingest_lambda': 'IngestUpload',
        'dynamo_lambda': 'dynamoLambda',
        'trigger_dynamo_autoscale': 'triggerDynamoAutoscale',
        'start_sfn_lambda': 'startSfnLambda',
        'index_id_writer_sfn': 'Index.IdWriter',
        'downsample_status': 'downsample-status',
        'downsample_dlq': 'downsample-dlq',
        'index_cuboid_supervisor_sfn': 'Index.CuboidSupervisor',
        'index_find_cuboids_sfn': 'Index.FindCuboids',
        'index_supervisor_sfn': 'Index.Supervisor',
        'index_enqueue_cuboids_sfn': 'Index.EnqueueCuboids',
        'index_fanout_enqueue_cuboids_sfn': 'Index.FanoutEnqueueCuboids',
        'index_dequeue_cuboids_sfn': 'Index.DequeueCuboids',
        'index_fanout_dequeue_cuboids_sfn': 'Index.FanoutDequeueCuboids',
        'index_fanout_id_writers_sfn': 'Index.FanoutIdWriters',
        'index_s3_writer_lambda': 'indexS3WriterLambda',
        'index_fanout_id_writer_lambda': 'indexFanoutIdWriterLambda',
        'index_write_id_lambda': 'indexWriteIdLambda',
        'index_deadletter_queue': 'indexDeadLetter',
        'index_write_failed_lambda': 'indexWriteFailedLambda',
        'index_find_cuboids_lambda': 'indexFindCuboidsLambda',
        'index_split_cuboids_lambda': 'indexSplitCuboidsLambda',
        'index_fanout_enqueue_cuboid_keys_lambda': 'indexFanoutEnqueueCuboidsKeysLambda',
        'index_batch_enqueue_cuboids_lambda': 'indexBatchEnqueueCuboidsLambda',
        'index_fanout_dequeue_cuboid_keys_lambda': 'indexFanoutDequeueCuboidsKeysLambda',
        'index_dequeue_cuboid_keys_lambda': 'indexDequeueCuboidsLambda',
        'index_get_num_cuboid_keys_msgs_lambda': 'indexGetNumCuboidKeysMsgsLambda',
        'index_check_for_throttling_lambda': 'indexCheckForThrottlingLambda',
        'index_invoke_index_supervisor_lambda': 'indexInvokeIndexSupervisorLambda',
        'index_load_ids_from_s3_lambda': 'indexLoadIdsFromS3Lambda',
        'index_cuboids_keys_queue': 'cuboidsKeys',
        'copy_cuboid_lambda': 'copyCuboidLambda',
        'copy_cuboid_dlq': 'copyCuboidDlq',
        'tile_uploaded_lambda': 'tileUploadLambda',
        'tile_ingest_lambda': 'tileIngestLambda'
    }

    def __getattr__(self, name):
        if name not in self.RESOURCES:
            raise AttributeError("{} is not a valid BOSS AWS Resource name".format(name))

        hostname = self.RESOURCES[name]
        if name in ['write_lock_topic']:
            return hostname

        fq_hostname = hostname + self.base_dot

        # Lambda names cannot have periods, so we use dashes, instead.
        if name in ['multi_lambda', 'write_lock', 'vault_monitor', 'consul_monitor', 'vault_consul_check',
                    'delete_lambda', 'ingest_lambda', 'dynamo_lambda', 
                    'index_s3_writer_lambda', 'index_fanout_id_writer_lambda',
                    'downsample_dlq', 'downsample_volume_lambda',
                    'delete_tile_objs_lambda', 'delete_tile_index_entry_lambda',
                    'index_write_id_lambda', 'index_write_failed_lambda',
                    'index_find_cuboids_lambda', 
                    'index_fanout_enqueue_cuboid_keys_lambda',
                    'index_batch_enqueue_cuboids_lambda', 
                    'index_fanout_dequeue_cuboid_keys_lambda',
                    'index_dequeue_cuboid_keys_lambda',
                    'index_get_num_cuboid_keys_msgs_lambda',
                    'index_check_for_throttling_lambda',
                    'index_invoke_index_supervisor_lambda',
                    'index_split_cuboids_lambda',
                    'index_load_ids_from_s3_lambda',
                    'start_sfn_lambda',
                    'delete_lambda', 'ingest_lambda', 'dynamo_lambda', 'downsample_dlq', 'downsample_volume_lambda',
                    'delete_tile_objs_lambda', 'delete_tile_index_entry_lambda',
                    'copy_cuboid_lambda', 'cuboid_import_lambda',
                    'volumetric_ingest_queue_upload_lambda', 'tile_ingest_lambda',
                    'tile_uploaded_lambda'
                    ]:
            fq_hostname = fq_hostname.replace('.','-')

        # Queue names cannot have periods, so we capitalize each word, instead.
        if name in ['s3flush_queue', 'deadletter_queue', 'delete_cuboid', 'query_deletes',
                    'ingest_queue_populate', 'ingest_queue_upload', 'resolution_hierarchy',
                    'downsample_volume', 'delete_experiment', 'delete_collection', 'delete_coord_frame',
                    'index_deadletter_queue', 'index_cuboids_keys_queue',
                    'ingest_cleanup_dlq', 'copy_cuboid_dlq']:
            fq_hostname = "".join(map(lambda x: x.capitalize(), fq_hostname.split('.')))

        return fq_hostname
'''

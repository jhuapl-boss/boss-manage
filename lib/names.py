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

def format_capitalize(fqdn):
    return "".join([x.capitalize() for x in fqdn.split('.')])

def format_dash(fqdn):
    return fqdn.replace('.', '-')

class AWSNameAccumulator(object):
    def __init__(self, initial_value, callback):
        self.acc = [initial_value]
        self.cb = callback

    def __repr__(self):
        """Display the partial AWSName so that it is easier to track
        down problems with json.dump"""
        return "<AWSNames().{}>".format('.'.join(self.acc))

    def __getattr__(self, key):
        self.acc.append(key)

        if len(self.acc) == 2:
            return self.cb(*self.acc)
        else:
            return self

    def __getitem__(self, key):
        return self.__getattr__(key)

    def __dir__(self):
        rtn = []
        # Assumes that the initial value is the resource name
        cfg = AWSNames.RESOURCES[self.acc[0]]
        if 'types' in cfg:
            rtn.extend(cfg['types'])
        if 'type' in cfg:
            rtn.append(cfg['type'])
        return rtn

class AWSNames(object):
    def __init__(self, internal_domain, external_domain=None, external_format=None, ami_suffix=None):
        self.internal_domain = internal_domain
        self.external_domain = external_domain
        self.external_format = external_format
        self.ami_suffix = ami_suffix

    @classmethod
    def from_bosslet(cls, bosslet_config):
        return cls(bosslet_config.INTERNAL_DOMAIN,
                   bosslet_config.EXTERNAL_DOMAIN,
                   bosslet_config.EXTERNAL_FORMAT,
                   bosslet_config.AMI_SUFFIX)

    @classmethod
    def from_lambda(cls, name):
        """
        Instantiate AWSNames from the name of a lambda function.  Used by
        lambdas so they can look up names of other resources.

        Args:
            name (str): Name of lambda function (ex: multiLambda-integration-boss)

        Returns:
            (AWSNames)

        """
        # NOTE: This will only allow looking up internal resource names
        #       external names or amis cannot be resolved

        # NOTE: Assume the format <lambda_name>-<internal_domain>
        #       where <lambda_name> doesn't have a - (or '.')
        # Lambdas names can't have periods; restore proper name.
        dotted_name = name.replace('-', '.')
        domain = dotted_name.split('.', 1)[1]
        return cls(domain)

    def public_dns(self, name):
        if not self.external_domain:
            raise ValueError("external_domain not provided")

        if self.external_format:
            name = self.external_format.format(machine = name)

        return name + '.' + self.external_domain

    def __getattr__(self, key):
        return AWSNameAccumulator(key, self.build)

    def __getitem__(self, key): # For dynamically building names from input
        return self.__getattr__(key)

    def __dir__(self):
        rtn = ['RESOURCES', 'TYPES',
               'public_dns', 'build',
               #'__getattr__', '__getitem__',
               'internal_domain', 'external_domain',
               'external_format', 'ami_suffix']
        rtn.extend(self.RESOURCES.keys())
        return rtn

    TYPES = {
        'stack': format_capitalize,
        'subnet': None,
        'dns': None, # Internal DNS name, EC2 and ELB
                     # XXX: maybe ec2, as it is an EC2 instance name
        'lambda_': format_dash, # Need '_' as lambda is a keyword
                                 # XXX: not all lambdas used dashes
        'rds': None,
        'sns': format_dash,
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
        'key': None, # KMS Key
    }

    RESOURCES = {
        # Ordered by name to make it easy to find an entry
        'activities': {'types': ['dns', 'ami', 'stack']},
        'api': {'type': 'stack'},
        'auth': {'types': ['dns', 'ami', 'sg']},
        'auth_db': {'name': 'auth-db',
                    'type': 'rds'},
        'bastion': {'type': 'dns'},
        'backup': {'types': ['ami', 's3', 'stack']},
        'cache': {'name': 'cache', # Redis server to cache cuboids
                  'type': 'redis'},
        'cachedb': {'type': 'stack'},
        'cachemanager': {'name': 'cachemanager',
                          'types': ['dns', 'ami']},
        'cache_session': {'name': 'cache-session', # Redis server for Django sessions
                          'type': 'redis'},
        'cache_state': {'name': 'cache-state',
                        'type': 'redis'},
        'cache_throttle': {'name': 'cache-throttle',
                           'types': ['redis', 'lambda_', 'cw']},
        'cloudwatch': {'type': 'stack'},
        'consul_monitor': {'name': 'consulMonitor',
                           'types': 'lambda_'},
        'copycuboid': {'type': 'stack'},
        'copy_cuboid_dlq': {'name': 'copyCuboidDlq',
                            'type': 'sqs'},
        'copy_cuboid_lambda': {'name': 'copyCuboidLambda',
                               'type': 'lambda_'},
        'core': {'type': 'stack'},
        'cuboid_bucket': {'name': 'cuboids',
                          'type': 's3'},
        'cuboid_import_dlq': {'name': 'cuboidImportDlq',
                              'type': 'sqs'},
        'cuboid_import_lambda': {'name': 'cuboidImportLambda',
                                 'type': 'lambda_'},
        'deadletter': {'name': 'Deadletter',
                       'type': 'sqs'},
        'default': {'type': 'rt'},
        'delete_bucket': {'name': 'delete',
                          'type': 's3'},
        'delete_collection': {'name': 'Delete.Collection',
                              'type': 'sfn'},
        'delete_coord_frame': {'name': 'Delete.CoordFrame',
                               'type': 'sfn'},
        'delete_cuboid': {'name': 'Delete.Cuboid',
                          'type': 'sfn'},
        'delete_eni': {'name': 'deleteENI',
                       'type': 'lambda_'},
        'delete_event_rule': {'name': 'deleteEventRule',
                              'type': 'dns'}, # XXX: rule type?
        'delete_experiment': {'name': 'Delete.Experiment',
                              'type': 'sfn'},
        'delete_tile_index_entry': {'name': 'deleteTileEntryLambda',
                                    'type': 'lambda_'},
        'delete_tile_objs': {'name': 'deleteTileObjsLambda',
                             'type': 'lambda_'},
        'dns': {'types': ['sns', 'lambda_']},
        'downsample_dlq': {'name': 'downsample-dlq',
                           'types': ['sqs', 'lambda_']},
        'downsample_volume': {'name': 'downsample.volume',
                              'type': 'lambda_'},
        'dynamolambda': {'type': 'stack'},
        'dynamo_lambda': {'name': 'dynamoLambda',
                          'type': 'lambda_'},
        'endpoint_db': {'name': 'endpoint-db',
                        'types': ['rds', 'dns']},
        'endpoint_elb': {'name': 'elb',
                         'type': 'dns'}, # XXX: elb type?
        'endpoint': {'types': ['dns', 'ami']},
        'external': {'type': 'subnet'},
        'https': {'type': 'sg'},
        'id_count_index': {'name': 'idCount',
                           'type': 'ddb'},
        'id_index': {'name': 'idIndex',
                     'type': 'ddb'},
        'idindexing': {'type': 'stack'},
        'index_batch_enqueue_cuboids': {'name': 'indexBatchEnqueueCuboidsLambda',
                                        'type': 'lambda_'},
        'index_check_for_throttling': {'name': 'indexCheckForThrottlingLambda',
                                       'type': 'lambda_'},
        'index_cuboids_keys': {'name': 'cuboidsKeys',
                               'type': 'sqs'},
        'index_cuboid_supervisor': {'name': 'Index.CuboidSupervisor',
                                    'type': 'sfn'},
        'index_deadletter': {'name': 'indexDeadLetter',
                             'type': 'sqs'},
        'index_dequeue_cuboid_keys': {'name': 'indexDequeueCuboidsLambda',
                                      'type': 'lambda_'},
        'index_dequeue_cuboids': {'name': 'Index.DequeueCuboids',
                                  'type': 'sfn'},
        'index_enqueue_cuboids': {'name': 'Index.EnqueueCuboids',
                                  'type': 'sfn'},
        'index_fanout_dequeue_cuboid_keys': {'name': 'indexFanoutDequeueCuboidsKeysLambda',
                                             'type': 'lambda_'},
        'index_fanout_dequeue_cuboids': {'name': 'Index.FanoutDequeueCuboids',
                                         'type': 'sfn'},
        'index_fanout_enqueue_cuboid_keys': {'name': 'indexFanoutEnqueueCuboidsKeysLambda',
                                             'type': 'lambda_'},
        'index_fanout_enqueue_cuboids': {'name': 'Index.FanoutEnqueueCuboids',
                                         'type': 'sfn'},
        'index_fanout_id_writer': {'name': 'indexFanoutIdWriterLambda',
                                   'type': 'lambda_'},
        'index_fanout_id_writers': {'name': 'Index.FanoutIdWriters',
                                    'type': 'sfn'},
        'index_find_cuboids': {'name': 'indexFindCuboidsLambda',
                               'types': ['lambda_', 'sfn']},
        'index_get_num_cuboid_keys_msgs': {'name': 'indexGetNumCuboidKeysMsgsLambda',
                                           'type': 'lambda_'},
        'index_id_writer': {'name': 'Index.IdWriter',
                            'type': 'sfn'},
        'index_invoke_index_supervisor': {'name': 'indexInvokeIndexSupervisorLambda',
                                          'type': 'lambda_'},
        'index_load_ids_from_s3': {'name': 'indexLoadIdsFromS3Lambda',
                                   'type': 'lambda_'},
        'index_s3_writer': {'name': 'indexS3WriterLambda',
                            'type': 'lambda_'},
        'index_split_cuboids': {'name': 'indexSplitCuboidsLambda',
                                'type': 'lambda_'},
        'index_supervisor': {'name': 'Index.Supervisor',
                             'type': 'sfn'},
        'index_write_failed': {'name': 'indexWriteFailedLambda',
                               'type': 'lambda_'},
        'index_write_id': {'name': 'indexWriteIdLambda',
                           'type': 'lambda_'},
        'ingest_bucket': {'name': 'ingest', # Cuboid staging area for volumetric ingests
                          'type': 's3'},
        'ingest_cleanup_dlq': {'name': 'IngestCleanupDlq',
                               'type': 'sqs'},
        'ingest_lambda': {'name': 'IngestUpload',
                          'type': 'lambda_'},
        'ingest_queue_populate': {'name': 'Ingest.Populate',
                                  'type': 'sfn'},
        'ingest_queue_upload': {'name': 'Ingest.Upload',
                                'type': 'sfn'},
        'internal': {'types': ['subnet', 'sg', 'rt']},
        'internet': {'types': ['rt', 'gw']},
        'meta': {'name': 'bossmeta',
                 'type': 'ddb'},
        'multi_lambda': {'name': 'multiLambda',
                         'type': 'lambda_'},
        'query_deletes': {'name': 'Query.Deletes',
                          'type': 'sfn'},
        'redis': {'type': 'stack'},
        'resolution_hierarchy': {'name': 'Resolution.Hierarchy',
                                 'type': 'sfn'},
        's3flush': {'name': 'S3flush',
                    'type': 'sqs'},
        's3_index': {'name': 's3index',
                     'type': 'ddb'},
        'ssh': {'type': 'sg'},
        'start_sfn': {'name': 'startSfnLambda',
                      'type': 'lambda_'},
        'test': {'type': 'stack'},
        'tile_bucket': {'name': 'tiles',
                        'type': 's3'},
        'tile_index': {'name': 'tileindex',
                       'type': 'ddb'},
        'tile_ingest': {'name': 'tileIngestLambda',
                        'type': 'lambda_'},
        'tile_uploaded': {'name': 'tileUploadLambda',
                          'type': 'lambda_'},
        'trigger_dynamo_autoscale': {'name': 'triggerDynamoAutoscale',
                                     'type': 'cw'},
        'vault_check': {'name': 'checkVault',
                               'type': 'cw'},
        'vault_monitor': {'name': 'vaultMonitor',
                          'type': 'lambda_'},
        'vault': {'types': ['dns', 'ami', 'ddb', 'key']},
        'volumetric_ingest_queue_upload': {'name': 'Ingest.Volumetric.Upload',
                                           'type': 'sfn'},
        'volumetric_ingest_queue_upload_lambda': {'name': 'VolumetricIngestUpload',
                                                  'type': 'lambda_'},
    }

    def build(self, name, resource_type):
        if resource_type not in self.TYPES:
            raise AttributeError("'{}' is not a valid resource type".format(resource_type))

        if name not in self.RESOURCES:
            raise AttributeError("'{}' is not a valid resource name".format(name))

        cfg = self.RESOURCES[name]
        if resource_type != cfg.get('type') and \
           resource_type not in cfg.get('types', []):
            raise AttributeError("'{}' is not a valid resource type for '{}'".format(resource_type, name))

        name = cfg.get('name', name)

        if self.TYPES[resource_type] is False:
            return name
        elif resource_type == 'ami':
            if not self.ami_suffix:
                raise ValueError("ami_suffix not provided")

            return name + self.ami_suffix
        else:
            fqdn = name + '.' + self.internal_domain

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
        "cachemanager": "cachemanager",
        "cache_db": "cachedb",
        "cuboid_bucket": "cuboids",
        "multi_lambda": "multiLambda",
        "s3_index": "s3index",
        "ingest_bucket": "ingest",          # Cuboid staging area For volumetric ingests.
        "tile_bucket": "tiles",
        "delete_tile_objs_lambda": 'deleteTileObjsLambda',
        "tile_index": "tileindex",
        "delete_tile_index_entry_lambda": 'deleteTileEntryLambda',
        "ingest_cleanup_dlq": "IngestCleanupDlq",
        "id_index": "idIndex",
        "id_count_index": "idCount",
        "s3flush_queue": "S3flush",
        "deadletter_queue": "Deadletter",
        'write_lock_topic': 'WriteLockAlert',
        'write_lock': 'WriteLockAlert',
        'vault_monitor': 'vaultMonitor',
        'vault_check': 'checkVault',
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
        'volumetric_ingest_queue_upload': 'Ingest.Volumetric.Upload',
        'volumetric_ingest_queue_upload_lambda': 'VolumetricIngestUpload',
        'ingest_lambda': 'IngestUpload',
        'dynamo_lambda': 'dynamoLambda',
        'trigger_dynamo_autoscale': 'triggerDynamoAutoscale',
        'start_sfn_lambda': 'startSfnLambda',
        'downsample_status': 'downsample-status',
        'downsample_dlq': 'downsample-dlq',
        'cuboid_import_lambda': 'cuboidImportLambda',
        'cuboid_import_dlq': 'cuboidImportDlq',
        'index_id_writer_sfn': 'Index.IdWriter',
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

        if name in ['multi_lambda', 'write_lock', 'vault_monitor', 'vault_check',
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

        if name in ['s3flush_queue', 'deadletter_queue', 'delete_cuboid', 'query_deletes',
                    'ingest_queue_populate', 'ingest_queue_upload', 'resolution_hierarchy',
                    'downsample_volume', 'delete_experiment', 'delete_collection', 'delete_coord_frame',
                    'index_deadletter_queue', 'index_cuboids_keys_queue',
                     'cuboid_import_dlq', 'ingest_cleanup_dlq', 'copy_cuboid_dlq', 'volumetric_ingest_queue_upload']:
            fq_hostname = "".join(map(lambda x: x.capitalize(), fq_hostname.split('.')))

        return fq_hostname
'''

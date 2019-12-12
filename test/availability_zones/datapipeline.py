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

import os, sys
import time

cur_dir = os.path.dirname(os.path.realpath(__file__))

# Allow `from lib import`
root_dir = os.path.normpath(os.path.join(cur_dir, '..', '..'))
sys.path.append(root_dir)

from lib import aws
from lib import constants as const
from lib import cloudformation
from lib import configuration
from lib import datapipeline
from lib.exceptions import BossManageError

def pipeline_status(bosslet_config, pipeline_id):
    client = bosslet_config.session.client('datapipeline')
    resp = client.describe_pipelines(pipelineIds=[pipeline_id])
    status = [f['stringValue']
              for f in resp['pipelineDescriptionList'][0]['fields']
              if f['key'] == '@healthStatus']

    if len(status) == 0:
        return None
    else:
        return status[0]

def pipeline_errors(bosslet_config, pipeline_id):
    client = bosslet_config.session.client('datapipeline')
    resp = client.query_objects(pipelineId=pipeline_id,
                                sphere='INSTANCE') # COMPONENT, INSTANCE, or ATTEMPT
    resp = client.describe_objects(pipelineId=pipeline_id,
                                   objectIds=resp['ids'])
    errors = [field['stringValue']
              for obj in resp['pipelineObjects']
              for field in obj['fields'] if field['key'] == '@failureReason']
    return errors

bosslet_config = configuration.BossConfiguration('test.boss')
config = cloudformation.CloudFormationConfiguration('test', bosslet_config)

config.add_vpc()
internal_subnets, external_subnets = config.add_all_subnets() # Add one subnet per AZ

ami = aws.ami_lookup(bosslet_config, const.BASTION_AMI)[0]

pipeline = datapipeline.DataPipeline()
for subnet in internal_subnets:
    AZ = subnet['Ref'][0]
    pipeline.add_shell_command(AZ + "TestCommand",
                               "/bin/echo this is a test",
                               runs_on = datapipeline.Ref(AZ + "TestInstance"))
    pipeline.add_ec2_instance(AZ + "TestInstance",
                              subnet=subnet,
                              type = 't1.micro',
                              image = ami)

config.add_data_pipeline("TestPipeline",
                         "test." + bosslet_config.INTERNAL_DOMAIN,
                         pipeline.objects)

azs = [sub['Ref'][0] for sub in internal_subnets]
print('Assigning a T1.Micro to each of the {} availability zones'.format(azs))
print()

try:
    config.create()
except BossManageError:
    print('Error detected, rolling back')
    client = bosslet_config.session.client('cloudformation')
    status = config._poll(client, config.stack_name, 'rollback', 'ROLLBACK_IN_PROGRESS')
    print('Stack status is: {}'.format(status))
    print()
    print('Errors:')
    for reason in config.get_failed_reasons():
        print('\t> {}'.format(reason))
    print('-------------------------')
else:
    print()
    print("Activating test pipeline")
    pipeline_id = aws.get_data_pipeline_id(bosslet_config.session, 'test.' + bosslet_config.INTERNAL_DOMAIN)
    aws.activate_data_pipeline(bosslet_config.session, pipeline_id)

    print("Waiting for pipeline ", end='', flush=True)
    while True:
        status = pipeline_status(bosslet_config, pipeline_id)
        if status is not None:
            break
        print(".", end='', flush=True)
        time.sleep(30)
    print(" {}".format(status))

    if status == 'ERROR':
        print("Errors:")
        for error in pipeline_errors(bosslet_config, pipeline_id):
            if 'create' not in error:
                continue
            print("\t> {}".format(error))
        print()
    else:
        print()
        print('\tNo availability zone restrictions on data pipeline subnet assignments')
        print()
finally:
    config.delete()


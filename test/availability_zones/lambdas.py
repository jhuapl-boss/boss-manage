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

cur_dir = os.path.dirname(os.path.realpath(__file__))

# Allow `from lib import`
root_dir = os.path.normpath(os.path.join(cur_dir, '..', '..'))
sys.path.append(root_dir)

from lib import aws
from lib import constants as const
from lib import cloudformation
from lib import configuration
from lib.exceptions import BossManageError

bosslet_config = configuration.BossConfiguration('test.boss')
config = cloudformation.CloudFormationConfiguration('test', bosslet_config)

config.add_vpc()
internal_subnets, external_subnets = config.add_all_subnets() # Add one subnet per AZ
config.add_security_group("InternalSecurityGroup",
                          bosslet_config.names.internal.sg,
                          [("-1", "-1", "-1", "10.0.0.0/8")])
config.add_lambda("TestLambda",
                  bosslet_config.names.dns.lambda_,
                  aws.role_arn_lookup(bosslet_config.session, 'lambda_cache_execution'),
                  const.DNS_LAMBDA,
                  handler="index.handler",
                  timeout=10,
                  security_groups=[cloudformation.Ref('InternalSecurityGroup')],
                  subnets=internal_subnets,
                  runtime='python3.7')

azs = [sub['Ref'][0] for sub in internal_subnets]
print('Assigning a lambda to the {} availability zones'.format(azs))
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
    print('\tNo availability zone restrictions on lambda subnet assignments')
    print()
finally:
    config.delete()

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
Create the cloudwatch alarms for the load balancer on top of a loadbalancer stack.The cloudwatch stack consists of
  * alarms monitor traffic in and out of the load balancer

"""

DEPENDENCIES = ['core', 'api']

from lib.cloudformation import CloudFormationConfiguration, Arg, Ref, Arn
from lib.userdata import UserData
from lib.keycloak import KeyCloakClient
from lib.exceptions import MissingResourceError
from lib import aws
from lib import utils
from lib import constants as const

import json

def create_config(bosslet_config):
    """Create the CloudFormationConfiguration object.
    :arg session used to perform lookups
    :arg domain DNS name of vpc
    """
    config = CloudFormationConfiguration('cloudwatch', bosslet_config)
    names = bosslet_config.names
    session = bosslet_config.session
    domain = bosslet_config.INTERNAL_DOMAIN

    vpc_id = config.find_vpc()
    lambda_subnets, _ = config.find_all_subnets(compatibility = 'lambda')

    internal_sg = aws.sg_lookup(session, vpc_id, names.internal.sg)

    loadbalancer_name = names.endpoint_elb.dns
    if not aws.lb_lookup(session, loadbalancer_name):
        raise MissingResourceError('ELB', loadbalancer_name)

    # TODO Test that MailingListTopic is working.
    production_mailing_list = bosslet_config.ALERT_TOPIC
    mailing_list_arn = aws.sns_topic_lookup(session, production_mailing_list)
    if mailing_list_arn is None:
        raise MissingResourceError('SNS topic', bosslet_config.ALERT_TOPIC)

    config.add_cloudwatch(loadbalancer_name, [mailing_list_arn])

    lambda_role = aws.role_arn_lookup(session, 'VaultConsulHealthChecker')
    config.add_arg(Arg.String(
        'VaultConsulHealthChecker', lambda_role,
        'IAM role for vault/consul health check'))

    config.add_lambda('VaultLambda',
                      names.vault_monitor.lambda_,
                      description='Check health of vault instances.',
                      timeout=30,
                      role=Ref('VaultConsulHealthChecker'),
                      security_groups=[internal_sg],
                      subnets=lambda_subnets,
                      handler='index.lambda_handler',
                      runtime='python3.7',
                      file=const.VAULT_LAMBDA)

    # Lambda input data
    json_str = json.dumps({
        'hostname': names.vault.dns,
    })

    config.add_cloudwatch_rule('VaultCheck',
                               name=names.vault_check.cw,
                               description='Check health of vault instances.',
                               targets=[
                                   {
                                       'Arn': Arn('VaultLambda'),
                                       'Id': names.vault_monitor.lambda_,
                                       'Input': json_str
                                   },
                               ],
                               schedule='rate(2 minutes)',
                               depends_on=['VaultLambda'])

    config.add_lambda_permission('VaultPerms',
                                 names.vault_monitor.lambda_,
                                 principal='events.amazonaws.com',
                                 source=Arn('VaultCheck'))

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

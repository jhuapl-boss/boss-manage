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
from lib.names import AWSNames
from lib.keycloak import KeyCloakClient
from lib.external import ExternalCalls
from lib import aws
from lib import utils
from lib import scalyr
from lib import constants as const

import json

def create_config(bosslet_config):
    """Create the CloudFormationConfiguration object.
    :arg session used to perform lookups
    :arg domain DNS name of vpc
    """
    config = CloudFormationConfiguration('cloudwatch', bosslet_config)
    names = AWSNames(bosslet_config)
    session = bosslet_config.session

    vpc_id = config.find_vpc()
    lambda_subnets, _ = config.find_all_subnets(compatibility = 'lambda')

    internal_sg = aws.sg_lookup(session, vpc_id, names.sg.internal)

    loadbalancer_name = names.dns.endpoint_elb
    if not aws.lb_lookup(session, loadbalancer_name):
        raise Exception("Invalid load balancer name: " + loadbalancer_name)

    # TODO Test that MailingListTopic is working.
    production_mailing_list = const.PRODUCTION_MAILING_LIST
    mailing_list_arn = aws.sns_topic_lookup(session, production_mailing_list)
    if mailing_list_arn is None:
        #config.add_sns_topic("topicList", production_mailing_list)
        msg = "MailingList {} needs to be created before running config"
        raise Exception(msg.format(const.PRODUCTION_MAILING_LIST))

    config.add_cloudwatch(loadbalancer_name, [mailing_list_arn])

    lambda_role = aws.role_arn_lookup(session, 'VaultConsulHealthChecker')
    config.add_arg(Arg.String(
        'VaultConsulHealthChecker', lambda_role,
        'IAM role for vault/consul health check'))

    config.add_lambda('VaultLambda',
                      names.lambda_.vault_monitor,
                      description='Check health of vault instances.',
                      timeout=30,
                      role=Ref('VaultConsulHealthChecker'),
                      security_groups=[internal_sg],
                      subnets=lambda_subnets,
                      handler='index.lambda_handler',
                      file=const.VAULT_LAMBDA)

    config.add_lambda('ConsulLambda',
                      names.lambda_.consul_monitor,
                      description='Check health of vault instances.',
                      timeout=30,
                      role=Ref('VaultConsulHealthChecker'),
                      security_groups=[internal_sg],
                      subnets=lambda_subnets,
                      handler='index.lambda_handler',
                      file=const.CONSUL_LAMBDA)

    # Lambda input data
    json_str = json.dumps({
        'vpc_id': vpc_id,
        'vpc_name': domain,
        'topic_arn': mailing_list_arn,
    })

    config.add_cloudwatch_rule('VaultConsulCheck',
                               name=names.cw.vault_consul_check,
                               description='Check health of vault and consul instances.',
                               targets=[
                                   {
                                       'Arn': Arn('VaultLambda'),
                                       'Id': names.lambda_.vault_monitor,
                                       'Input': json_str
                                   },
                                   {
                                       'Arn': Arn('ConsulLambda'),
                                       'Id': names.lambda_.consul_monitor,
                                       'Input': json_str
                                   },
                               ],
                               schedule='rate(1 minute)',
                               depends_on=['VaultLambda', 'ConsulLambda'])

    config.add_lambda_permission('VaultPerms',
                                 names.lambda_.vault_monitor,
                                 principal='events.amazonaws.com',
                                 source=Arn('VaultConsulCheck'))

    config.add_lambda_permission('ConsulPerms',
                                 names.lambda_.consul_monitor,
                                 principal='events.amazonaws.com',
                                 source=Arn('VaultConsulCheck'))

    return config


def generate(bosslet_config):
    """Create the configuration and save it to disk"""
    config = create_config(bosslet_config)
    config.generate()

def create(bosslet_config):
    config = create_config(bosslet_config)

    success = config.create()

    if success:
        print('success')
    else:
        print('failed')

    return success

def update(session, domain):
    config = create_config(bosslet_config)
    success = config.update()
    return success

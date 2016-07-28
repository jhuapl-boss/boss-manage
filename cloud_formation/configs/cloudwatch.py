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


import configuration
import library as lib


def create_vault_consul_health_checks(session, domain, vpc_id, config):
    """Update CloudFormationConfiguration with resources for vault and consul health checks.

    Add lambda functions for monitoring and responding to failed health checks
    of the vault and consul instances.

    Args:
        session (boto3.Session): Active Boto3 session.
        domain (string): DNS name of VPC.
        vpc_id (string): Physical id of VPC.
        config (CloudFormationConfiguration): config to update.
    """
    lambda_role = 'arn:aws:iam::256215146792:role/VaultConsulHealthChecker'
    config.add_arg(configuration.Arg.String(
        'VaultConsulHealthChecker', lambda_role,
        'IAM role for vault/consul health check.' + domain))

    core_sec_group = lib.sg_lookup(session, vpc_id, 'internal.' + domain)
    filter_by_host_name = ([{
        'Name': 'tag:Name',
        'Values': ['*internal.' + domain]
    }])
    subnets = lib.multi_subnet_id_lookup(session, filter_by_host_name)

    chk_vault_lambda = 'vaultMonitor'
    chk_vault_lambda_logical_name = (
        chk_vault_lambda + '-' + domain.replace('.', '-'))
    config.add_lambda(
        key=chk_vault_lambda,
        name=chk_vault_lambda_logical_name,
        description='Check health of vault instances.',
        timeout=20,
        role='VaultConsulHealthChecker',
        security_groups=[core_sec_group],
        subnets=subnets,
        handler='index.lambda_handler',
        file='lambda/monitors/chk_vault.py',
        )

    chk_consul_lambda = 'consulMonitor'
    chk_consul_lambda_logical_name = (
        chk_consul_lambda + '-' + domain.replace('.', '-'))
    config.add_lambda(
        key=chk_consul_lambda,
        name=chk_consul_lambda_logical_name,
        description='Check health of vault instances.',
        timeout=20,
        role='VaultConsulHealthChecker',
        security_groups=[core_sec_group],
        subnets=subnets,
        handler='index.lambda_handler',
        file='lambda/monitors/chk_consul.py',
        )

    vault_consul_topic = 'vaultConsulAlert'
    vault_consul_topic_logical_name = (
        vault_consul_topic + '-' + domain.replace('.', '-'))
    vault_consul_subscribers = []
    config.add_sns_topic(
        vault_consul_topic, vault_consul_topic,
        vault_consul_topic_logical_name, vault_consul_subscribers)

    # json for rule's Input key.  Split into a list so it can be passed to
    # Fn::Join for execution of the Ref function.
    json_str_list = [
        """{{
            "vpc_id": "{}",
            "vpc_name": "{}",
            "topic_arn": \"""".format(vpc_id, domain),
        { 'Ref': '{}'.format(vault_consul_topic) },
        '"}']

    chk_vault_consul_rule_name = 'checkVaultConsul'
    chk_vault_consul_rule_logical_name = (
        chk_vault_consul_rule_name + '-' + domain.replace('.', '-'))
    config.add_cloudwatch_rule(
        key=chk_vault_consul_rule_name,
        targets=[
            {
                'Arn': { 'Fn::GetAtt': [chk_vault_lambda, 'Arn']},
                'Id': chk_vault_lambda_logical_name,
                'Input': { 'Fn::Join': ['', json_str_list] }
            },
            {
                'Arn': { 'Fn::GetAtt': [chk_consul_lambda, 'Arn']},
                'Id': chk_consul_lambda_logical_name,
                'Input': { 'Fn::Join': ['', json_str_list] }
            },
        ],
        name=chk_vault_consul_rule_logical_name,
        schedule='rate(1 minute)',
        description='Check health of vault and consul instances.',
        depends_on=[vault_consul_topic, chk_vault_lambda, chk_consul_lambda]
        )

    config.add_lambda_permission(
        'chkVaultConsulExecute', chk_vault_lambda,
        principal='events.amazonaws.com',
        source={'Fn::GetAtt': [chk_vault_consul_rule_name, 'Arn']})

    config.add_lambda_permission(
        'chkVaultConsulExecute', chk_consul_lambda,
        principal='events.amazonaws.com',
        source={'Fn::GetAtt': [chk_vault_consul_rule_name, 'Arn']})


def create_config(session, domain, keypair=None, user_data=None, db_config={}):
    """Create the CloudFormationConfiguration object.
    :arg session used to perform lookups
    :arg domain DNS name of vpc
    :arg keypair AWS keypair used to instantiate
    :arg user_data custom data needed for config
    :arg db_config database config
    """
    config = configuration.CloudFormationConfiguration(domain)

    # do a couple of verification checks
    if config.subnet_domain is not None:
        raise Exception("Invalid VPC domain name")

    vpc_id = lib.vpc_id_lookup(session, domain)
    if session is not None and vpc_id is None:
        raise Exception("VPC does not exists, exiting...")

    # Lookup the VPC, External Subnet, that are needed by other resources
    config.add_arg(configuration.Arg.VPC("VPC", vpc_id,
                                         "ID of VPC to create resources in"))

    loadbalancer_name = "elb-" + domain.replace(".", "-")  # elb names can't have periods in them.
    is_lb = lib.lb_lookup(session, loadbalancer_name)
    if not is_lb:
        raise Exception("Invalid load balancer name: " + loadbalancer_name)

    # TODO Test that MailingListTopic is working.
    production_mailing_list = "ProductionMicronsMailingList"
    mailingListTopic = lib.sns_topic_lookup(session, production_mailing_list)
    if mailingListTopic is None:
        #config.add_sns_topic("topicList", production_mailing_list)
        raise Exception("MailingList " + production_mailing_list + "needs to be created before running cloudwatch")

    config.add_cloudwatch( loadbalancer_name, mailingListTopic)

    # Add lambda functions.
    create_vault_consul_health_checks(session, domain, vpc_id, config)

    return config


def generate(folder, domain):
    """Create the configuration and save it to disk
    :arg folder location to generate the cloudformation template stack
    :arg domain internal DNS name"""
    name = lib.domain_to_stackname("loadbalancer." + domain)
    config = create_config(None, domain)
    config.generate(name, folder)


def create(session, domain):
    """Create the configuration, launch it, and initialize Vault
    :arg session information for performing lookups
    :arg domain internal DNS name """
    name = lib.domain_to_stackname("cloudwatch." + domain)
    config = create_config(session, domain)

    success = config.create(session, name)

    if success:
        print('success')
    else:
        print('failed')

def delete(session, domain):
    # Expect to add custom delete.

    # Standard stack delete.
    lib.delete_stack(session, domain, "cloudwatch")

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
Create the cachedb configuration which consists of

  * An cachmanager server to run three daemons for
        * cache-write
        * cache-miss
        * cache-delayed write
  * Lambdas
  * SNS topics
  * SQS queues

This will most likely be merged into production once it is finished.

"""


import configuration
import library as lib
import hosts
import json
import scalyr
import uuid
import sys
import boto3
import os
import subprocess
import tempfile
import shlex
cur_dir = os.path.dirname(os.path.realpath(__file__))
vault_dir = os.path.normpath(os.path.join(cur_dir, "..", "vault"))
sys.path.append(vault_dir)
import bastion
from ssh import *


# Region production is created in.  Later versions of boto3 should allow us to
# extract this from the session variable.  Hard coding for now.
PRODUCTION_REGION = 'us-east-1'

INCOMING_SUBNET = "52.3.13.189/32"  # microns-bastion elastic IP

CACHE_MANAGER_TYPE = {
    "development": "t2.micro",
    "production": "t2.medium",
}


def create_config(session, domain, keypair=None, user_data=None):
    """
    Create the CloudFormationConfiguration object.
    Args:
        session: amazon session object
        domain: domain of the stack being created
        keypair: keypair used to by instances being created
        user_data: information used by the endpoint instance and vault
        db_config: information needed by rds

    Returns: the config for the Cloud Formation stack

    """
    config = configuration.CloudFormationConfiguration(domain, PRODUCTION_REGION)

    # do a couple of verification checks
    if config.subnet_domain is not None:
        raise Exception("Invalid VPC domain name")

    vpc_id = lib.vpc_id_lookup(session, domain)
    if session is not None and vpc_id is None:
        raise Exception("VPC does not exists, exiting...")

    # Lookup the VPC, External Subnet, Internal Security Group IDs that are
    # needed by other resources
    config.add_arg(configuration.Arg.VPC("VPC", vpc_id,
                                         "ID of VPC to create resources in"))

    external_subnet_id = lib.subnet_id_lookup(session, "external." + domain)
    config.add_arg(configuration.Arg.Subnet("ExternalSubnet",
                                            external_subnet_id,
                                            "ID of External Subnet to create resources in"))

    internal_subnet_id = lib.subnet_id_lookup(session, "internal." + domain)
    config.add_arg(configuration.Arg.Subnet("InternalSubnet",
                                            internal_subnet_id,
                                            "ID of Internal Subnet to create resources in"))

    internal_sg_id = lib.sg_lookup(session, vpc_id, "internal." + domain)
    config.add_arg(configuration.Arg.SecurityGroup("InternalSecurityGroup",
                                                   internal_sg_id,
                                                   "ID of internal Security Group"))

    config.add_ec2_instance("CacheManager",
                                "cachemanager." + domain,
                                lib.ami_lookup(session, "cachemanager.boss"),
                                keypair,
                                subnet="InternalSubnet",
                                public_ip=False,
                                type_=CACHE_MANAGER_TYPE,
                                security_groups=["InternalSecurityGroup"],
                                user_data=user_data,
                                role="cachemanager") # arn:aws:iam::256215146792:instance-profile/cachemanager"

    lambda_sec_group = lib.sg_lookup(session, vpc_id, 'internal.' + domain)
    filter_by_host_name = ([{
        'Name': 'tag:Name',
        'Values': ['*internal.' + domain]
    }])
    lambda_subnets = lib.multi_subnet_id_lookup(session, filter_by_host_name)

    config.add_lambda("MultiLambda",
                      "multiLambda." + domain,
                      "LambdaCacheExecutionRole",
                      s3=("boss-lambda-env",
                          "lambda.{}.zip".format(domain),
                          "local/lib/python3.4/site-packages/lambda/lambda_loader.handler"),
                      timeout=60,
                      security_groups=[lambda_sec_group],
                      subnets=lambda_subnets)

    role = lib.role_arn_lookup(session, "lambda_cache_execution")
    config.add_arg(configuration.Arg.String("LambdaCacheExecutionRole", role,
                                            "IAM role for multilambda." + domain))
    return config


def generate(folder, domain):
    """Create the configuration and save it to disk"""
    name = lib.domain_to_stackname("cachedb." + domain)
    config = create_config(None, domain)
    config.generate(name, folder)


def create(session, domain):
    """Create the configuration, and launch it"""
    user_data = configuration.UserData()
    user_data["system"]["fqdn"] = "cachemanager." + domain
    user_data["system"]["type"] = "cachemanager"
    user_data["aws"]["cache"] = "cache." + domain
    user_data["aws"]["cache-state"] = "cache-state." + domain
    user_data["aws"]["cache-db"] = '0'  ## cache-db and cache-stat-db need to be in user_data for lambda to get to them.
    user_data["aws"]["cache-state-db"] = '0'

    keypair = lib.keypair_lookup(session)

    try:
        name = lib.domain_to_stackname("cachedb." + domain)
        pre_init(session, domain)
        config = create_config(session, domain, keypair, str(user_data))

        success = config.create(session, name)
        print("finished config.create")
        if not success:
            raise Exception("Create Failed")
        else:
            post_init(session, domain)
    except:
        print("Error detected") # Do we want to revoke if an exception from post_init?
        raise


def pre_init(session, domain):
    # zip up spdb, bossutils, lambda and lambda_utils
    tempname = tempfile.NamedTemporaryFile(delete=True)
    zipname = tempname.name + '.zip'
    print('Using temp zip file: ' + zipname)
    cwd = os.getcwd()
    os.chdir('../salt_stack/salt/spdb/files')
    lib.write_to_zip('spdb.git', zipname, False)
    os.chdir(cwd)
    os.chdir('../salt_stack/salt/boss-tools/files/boss-tools.git')
    lib.write_to_zip('bossutils', zipname)
    lib.write_to_zip('lambda', zipname)
    lib.write_to_zip('lambdautils', zipname)

    keypair = os.environ.get("SSH_KEY", None);
    print("Copying local modules to lambda-build-server")

    #copy the zip file to lambda_build_server
    apl_bastion_ip = os.environ.get("BASTION_IP")
    apl_bastion_key = os.environ.get("BASTION_KEY")
    apl_bastion_user = os.environ.get("BASTION_USER")
    local_port = bastion.locate_port()
    proc = bastion.create_tunnel(apl_bastion_key, local_port, "52.23.27.39", 22, apl_bastion_ip, bastion_user="ubuntu")
    scp_cmd = "scp -P {} {} {} ec2-user@localhost:sitezips/{}".format(local_port,
                                                                      bastion.SSH_OPTIONS,
                                                                      zipname,
                                                                      domain + ".zip")
    try:
        return_code = subprocess.call(shlex.split(scp_cmd))  # close_fds=True, preexec_fn=bastion.become_tty_fg
        print("scp return code: " + str(return_code))
    finally:
        proc.terminate()
        proc.wait()
    os.remove(zipname)

    # This section will run makedomainenv on lambda-build-server however
    # running it this way seems to cause the virtualenv to get messed up.
    # Running this script manually on the build server does not have the problem.
    # cmd = "\"source /home/ec2-user/makedomainenv {}\"".format(domain)
    # ssh(apl_bastion_key, "52.23.27.39", "ec2-user", cmd)


def post_init(session, domain):
    print("post_init")

    # Tell Scalyr to get CloudWatch metrics for these instances.
    instances = ["cachemanager." + domain]
    scalyr.add_instances_to_scalyr(
        session, PRODUCTION_REGION, instances)



def delete(session, domain):
    # NOTE: CloudWatch logs for the DNS Lambda are not deleted
    lib.delete_stack(session, domain, "cachedb")
    lib.route53_delete_records(session, domain, "cachemanager." + domain)



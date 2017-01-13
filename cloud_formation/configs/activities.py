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

from lib.cloudformation import CloudFormationConfiguration, Ref, Arn, get_scenario, Arg
from lib.userdata import UserData
from lib.names import AWSNames
from lib import aws
from lib import utils
from lib import scalyr
from lib import constants as const
from lib import stepfunctions as sfn

keypair = None


def create_config(session, domain):
    """Create the CloudFormationConfiguration object."""
    config = CloudFormationConfiguration('activities', domain, const.REGION)
    names = AWSNames(domain)

    global keypair
    keypair = aws.keypair_lookup(session)

    vpc_id = config.find_vpc(session)
    az_subnets, external_subnets = config.find_all_availability_zones(session)
    sgs = aws.sg_lookup_all(session, vpc_id)

    internal_subnet_id = aws.subnet_id_lookup(session, names.subnet("internal"))
    config.add_arg(Arg.Subnet("InternalSubnet",
                              internal_subnet_id,
                              "ID of Internal Subnet to create resources in"))

    user_data = UserData()
    user_data["system"]["fqdn"] = names.activities
    user_data["system"]["type"] = "activities"

    config.add_ec2_instance("Activities",
                            names.activities,
                            aws.ami_lookup(session, 'activities.boss'),
                            keypair,
                            subnet = Ref("InternalSubnet"),
                            role = "activity",
                            user_data = str(user_data),
                            security_groups = [sgs[names.internal]])

    return config


def generate(session, domain):
    """Create the configuration and save it to disk"""
    config = create_config(session, domain)
    config.generate()


def create(session, domain):
    """Create the configuration, launch it, and initialize Vault"""
    config = create_config(session, domain)

    success = config.create(session)
    if success:
        post_init(session, domain)

def post_init(session, domain, startup_wait=False):
    names = AWSNames(domain)

    sfn.create(session, names.delete_cuboid, domain, 'delete_cuboid.sfn', 'StatesExecutionRole-us-east-1 ')

def delete(session, domain):
    names = AWSNames(domain)
    # DP TODO: delete activities
    CloudFormationConfiguration('activities', domain).delete(session)

    sfn.delete(session, names.delete_cuboid)

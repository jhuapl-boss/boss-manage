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

from lib import hosts
from lib import aws
from lib.cloudformation import CloudFormationConfiguration, Ref
from lib.names import AWSNames

def create_config(session, domain, peer_domain):
    config = CloudFormationConfiguration('peer', domain)

    # Reconfigure the stack name from the default
    stack_name = domain + ".to." + peer_domain
    config.stack_name = "".join([x.capitalize() for x in stack_name.split('.')])

    vpc_id = aws.vpc_id_lookup(session, domain)
    vpc_subnet = hosts.lookup(domain)
    names = AWSNames(domain)

    peer_id = aws.vpc_id_lookup(session, peer_domain)
    peer_subnet = hosts.lookup(peer_domain)
    peer_names = AWSNames(peer_domain)
    
    if session is not None:
        if vpc_id is None:
            raise Exception("VPC does not exist, exiting...")
            
        if peer_id is None:
            raise Exception("Peer VPC does not exist, existing...")
    
    config.add_vpc_peering("Peer",
                           vpc_id,
                           peer_id)
                           
    def add_route(key, vpc_id_, rt_name, vpc_subnet_):
        rt = aws.rt_lookup(session, vpc_id_, rt_name)
        config.add_route_table_route(key, rt, vpc_subnet_, peer = Ref("Peer"))
    
    add_route("PeeringRoute", vpc_id, names.internal, peer_subnet)
    add_route("PeeringRoute2", vpc_id, names.internet, peer_subnet)
    add_route("PeerPeeringRoute", peer_id, peer_names.internal, vpc_subnet)
    add_route("PeerPeeringRoute2", peer_id, peer_names.internet, vpc_subnet)

    return config
    
def generate(session, domain):
    peer_vpc = input("Peer VPC: ")

    config = create_config(session, domain, peer_vpc)
    config.generate()
    
def create(session, domain):
    peer_vpc = input("Peer VPC: ")

    config = create_config(session, domain, peer_vpc)
    config.create(session)
    
def delete(session, domain):
    peer_vpc = input("Peer VPC: ")

    config = create_config(session, domain, peer_vpc)
    config.delete(session)


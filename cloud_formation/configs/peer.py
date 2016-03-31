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

import library as lib
import configuration
import hosts

def create_config(session, domain, peer_domain):
    config = configuration.CloudFormationConfiguration(domain)

    if config.subnet_domain is not None:
        raise Exception("Invalid VPC domain name")

    vpc_id = lib.vpc_id_lookup(session, domain)
    vpc_subnet = hosts.lookup(domain)
    peer_id = lib.vpc_id_lookup(session, peer_domain)
    peer_subnet = hosts.lookup(peer_domain)
    
    if session is not None:
        if vpc_id is None:
            raise Exception("VPC does not exist, exiting...")
            
        if peer_id is None:
            raise Exception("Peer VPC does not exist, existing...")
    
    config.add_vpc_peering("Peer",
                           vpc_id,
                           peer_id)
                           
    def add_route(key, rt_key, rt_name, vpc_subnet_, vpc_id_):
        config.add_route_table_route(key, rt_key, vpc_subnet_, peer = "Peer")
        config.add_arg(configuration.Arg.RouteTable(rt_key,
                                                    lib.rt_lookup(session, vpc_id_, rt_name)))
    
    add_route("PeeringRoute", "LocalRouteTable", "internal." + domain, peer_subnet, vpc_id)
    add_route("PeeringRoute2", "LocalInternetRouteTable", "internet." + domain, peer_subnet, vpc_id)
    add_route("PeerPeeringRoute", "PeerRouteTable", "internal." + peer_domain, vpc_subnet, peer_id)
    add_route("PeerPeeringRoute2", "PeerInternetRouteTable", "internet." + peer_domain, vpc_subnet, peer_id)

    return config
    
def generate(folder, domain):
    name = lib.domain_to_stackname(domain)
    config = create_config(None, domain)
    config.generate(name, folder)
    
def create(session, domain):
    peer_vpc = input("Peer VPC: ")

    name = lib.domain_to_stackname(domain + ".to." + peer_vpc)
    config = create_config(session, domain, peer_vpc)
    
    success = config.create(session, name)
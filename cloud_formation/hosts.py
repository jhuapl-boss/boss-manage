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

"""Library for looking up IP subnets and IP addresses by name.

TLD - The Top Level Domain name for internal naming.
BASE_IP / ROOT_CIDR - The top level subnet in which to start numbering.
VPC_CIDR - The CIDR number for VPCs.
SUBNET_CIDR - The CIDR number for Subnets.

NOTE: BASE_CIDR < VPC_CIDR < SUBNET_CIDR

VPCS - A dictionary of names and Subnet number for each valid VPC.
SUBNETS - A dictionary of names and Subnet number for each valid Subnet.
STATIC - A dictionary of hostnames and IP address that are static and should
         always be available
"""

##
# User configurable section. Changes here will change how addresses are generated
#
# Note: The first three (3) address in each subnet are reserved by AWS
#       http://docs.aws.amazon.com/AmazonVPC/latest/UserGuide/VPC_Subnets.html
#       Section Subnet Sizing
# Example: For 10.0.0.0/24 Subnet
#          10.0.0.0: Network address.
#          10.0.0.1: Reserved by AWS for the VPC router.
#          10.0.0.2: Reserved by AWS for mapping to the Amazon-provided DNS.
#          10.0.0.3: Reserved by AWS for future use.
#          10.0.0.255: Network broadcast address. We do not support broadcast in a VPC, therefore we reserve this address.
##

TLD = "boss"
BASE_IP = "10.0.0.0"
ROOT_CIDR = 8
VPC_CIDR = 16 # make sure VPC_CIDR is greater than ROOT_CIDR
SUBNET_CIDR = 24 # make sure SUBNET_CIDR is greater than VPC_CIDR

# Name and Subnet number (must fit within ROOT_CIDR to VPC_CIDR) of all VPCs
VPCS = {
    "production" : 0,

    "integration" : 20,

    "test" : 40,

    "pryordm1" : 100,
    "breinmw1" : 101,
    "drenkng1" : 102,
    "giontc1"  : 103,
    "hiderrt1" : 104,
    "kleisdm1" : 105,
    "leea1"    : 106,
    "manavpj1" : 107,

}

# Name of the VPC, Name of the Subnet and the Subnet's Subnet number (must fit within VPC_CIDR to SUBNET_CIDR) for all Subnets
SUBNETS = {
}

# Dynamically add the following subnets to all VPCs
for vpc in VPCS:
    # not all regions have all availability zones, but reserve them
    subnets = ["internal", "external",
               "a-internal", "b-internal", "c-internal", "d-internal", "e-internal",
               "a-external", "b-external", "c-external", "d-external", "e-external"]
    for subnet in subnets:
        SUBNETS[(vpc, subnet)] = subnets.index(subnet)

# Static hostname, IP address enteries
STATIC = {
}


# domains listed in this dictionary have certificates for the auth and api loadbalancers to use.
BASE_DOMAIN_CERTS = {"production.boss": "theboss.io",
                      "integration.boss": "integration.theboss.io",
                      "hiderrt1.boss": "hiderrt1.theboss.io"}


##
# Generation Code
##

import sys
from ipaddress import IPv4Network

def get_subnet(network, subnet_cidr, subnet_id):
    """Subnet a IPv4Network and select subnet number <subnet_id>."""
    if type(network) != IPv4Network:
        network = IPv4Network(network)

    return list(network.subnets(new_prefix=subnet_cidr))[subnet_id]

def get_ip(network, vpc_id, subnet_id, device_id):
    """Given a starting network, find the vpc_id and subnet_id subnets, and
    then select ip address number <device_id>.
    """
    vpc_net = get_subnet(network, VPC_CIDR, vpc_id)
    sub_net = get_subnet(vpc_net, SUBNET_CIDR, subnet_id)
    device_ip = list(sub_net)[device_id]
    return device_ip

def get_entry(network, vpc_name, subnet_name, device_name, device_id):
    """Given a starting network and the hostname components of a device,
    generate the IP address and full hostname.
    """
    ip = get_ip(network, VPCS[vpc_name], SUBNETS[(vpc_name, subnet_name)], device_id)
    name = ".".join([device_name, subnet_name, vpc_name, TLD])

    return ip, name

def gen_hosts(domain, devices):
    """Itterate through all devices enteries to generate the set of IP
    addresses and full hostnames for every device.

    STATIC enteries are added to the results before being returned.
    """
    base_net = IPv4Network(BASE_IP + "/" + str(ROOT_CIDR))
    addresses = {}

    subnet_name, vpc_name, tld = domain.split(".")

    for device in expand_devices(devices):
        device_id = devices[device]
        ip,name = get_entry(base_net, vpc_name, subnet_name, device, device_id)
        addresses[ip] = name

    for hostname in STATIC:
        addresses[STATIC[hostname]] = hostname

    return addresses

def expand_devices(devices):
    """Expand the range() and [] values in devices. Each value in the list
    gets a unique hostname with the first hostname being the dictionary key
    all following hostnames adding an incrementing number (web, web2, web3,
    ...) .
    """
    rtn = {}

    for device in devices:
        device_id = devices[device]
        if type(device_id) == range:
            device_id = list(device_id)
        if type(device_id) == list:
            for i in device_id:
                i_idx = device_id.index(i)
                device_name = device + (str(i_idx) if i_idx > 0 else "")
                rtn[device_name] = i
        else:
            rtn[device_name] = device_id

    return rtn

def lookup(domain, devices=None):
    """Locate the subnet or IP address for the given domain name.

    If the domain is not a VPC or Subnet and is not in STATIC then devices is
    required to be specified and the dictionary is used to complete the
    lookup.
    """
    if domain in STATIC:
        return STATIC[domain]

    parts = domain.split(".")

    get_next = lambda: parts.pop() if len(parts) > 0 else None

    tld = get_next()
    if tld !=  TLD:
        print("ERROR: '{}' is not the valid TLD".format(tld))
        return None
    else:
        base_net = IPv4Network(BASE_IP + "/" + str(ROOT_CIDR))
        if len(parts) == 0:
            return str(base_net)

    vpc_name = get_next()
    if vpc_name not in VPCS:
        print("ERROR: '%s' is not a valid VPC name".format(vpc_name))
        return None
    else:
        vpc_net = get_subnet(base_net, VPC_CIDR, VPCS[vpc_name])
        if len(parts) == 0:
            return str(vpc_net)

    subnet_name = get_next()
    subnet_key = (vpc_name, subnet_name)
    if subnet_key not in SUBNETS:
        print("ERROR: '{}' is not a valid Subnet name for VPC '{}'".format(subnet_name, vpc_name))
        return None
    else:
        subnet_net = get_subnet(vpc_net, SUBNET_CIDR, SUBNETS[subnet_key])
        if len(parts) == 0:
            return str(subnet_net)

    if len(parts) != 0 and devices is None:
        print("ERROR: Need devices to lookup device hostname")
        return None

    devices = expand_devices(devices)
    device_name = get_next()
    if device_name not in devices:
        print("ERROR: '{}' is not a valid device name for Subnet '{}'".format(device_name, subnet_name))
        return None
    else:
        device_ip, _ = get_entry(base_net, vpc_name, subnet_name, device_name, devices[device_name])
        return str(device_ip)
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

"""Library containing IP subnet and SSL cert lookups.

Library contains AWS VPC and VPC Subnet IP subnet allocation and lookup.

Library contains SSL cert mapping between AWS VPC name and external DNS root


TLD : The Top Level Domain name for internal naming.
BASE_IP / ROOT_CIDR : The top level subnet in which to start numbering.
VPC_CIDR : The CIDR number for VPCs.
SUBNET_CIDR : The CIDR number for Subnets.

NOTE: BASE_CIDR < VPC_CIDR < SUBNET_CIDR

VPCS : A dictionary of names and Subnet number for each valid VPC.
       VPCS[vpc] = subnet index
SUBNETS : A dictionary of names and Subnet number for each valid Subnet (per VPC)
          SUBNETS[(vpc, subnet)] = subnet index

BASE_DOMAIN_CERTS : A dictionary of VPC names and external DNS roots
                    BASE_DOMAIN_CERTS[vpc.boss] = external DNS root

Author:
    Derek Pryor <Derek.Pryor@jhuapl.edu>
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

LAMBDA_SUBNETS = 16 # TODO merge with constants.py variable of the same name

# DP TODO: Migrate to constants.py
PROD_ACCOUNT = "451493790433"
PROD_DOMAIN = "theboss.io"
PROD_LAMBDA_BUCKET = "boss-lambda-prod-env"
PROD_LAMBDA_SERVER = "54.210.116.141"

# Below is the old lambda server that targets Python 3.4 in the lambda
# deployment package.
#PROD_LAMBDA_SERVER = "52.55.121.6"

DEV_ACCOUNT = "256215146792"
DEV_DOMAIN = "thebossdev.io"
DEV_LAMBDA_BUCKET = "boss-lambda-env"
DEV_LAMBDA_SERVER = "52.23.27.39"

# Below is the old lambda server that targets Python 3.4 in the lambda
# deployment package. 
#DEV_LAMBDA_SERVER = "54.91.22.179"


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
    "davismj1" : 108,

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
    for i in range(LAMBDA_SUBNETS):
        subnets.append('lambda{}'.format(i))

    # New subnets have to be added at the end of the subnet list
    # Because other subnets already have CIDR Ranges. This avoids conflicts when updating Integration or Production
    subnets.append("f-internal")
    subnets.append("f-external")

    for subnet in subnets:
        SUBNETS[(vpc, subnet)] = subnets.index(subnet)

# domains listed in this dictionary have certificates for the auth and api loadbalancers to use.
BASE_DOMAIN_CERTS = {"production.boss": PROD_DOMAIN,
                      "integration.boss": "integration.{}".format(PROD_DOMAIN)}


##
# Generation Code
##

import sys
from ipaddress import IPv4Network

def get_subnet(network, subnet_cidr, subnet_id):
    """Lookup the specific subnet from the current network.

    Args:
        network (IPv4Network|string) : Starting network to derive the subnet from
        subnet_cidr (int) : The CIDR used to divide network into
        subnet_id (int) : Which of the subnet_cidr divided network subnets to select

    Returns:
        (IPv4Network) : The select subnet
    """
    if type(network) != IPv4Network:
        network = IPv4Network(network)

    return list(network.subnets(new_prefix=subnet_cidr))[subnet_id]

def lookup(domain):
    """Lookup the subnet of the given domain name.

        Note: domain should be in the format of vpc.boss or subnet.vpc.boss

    Args:
        domain (string) : domain name to locate the subnet of

    Returns:
        (string|None) : String containing the subnet in CIDR format or None if
                        the domain is not a valid BOSS vpc or subnet domain name
    """

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

    print("ERROR: domain contains extra information beyond Subnet and VPC")
    return None

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("Usage: {} domain".format(sys.argv[0]))
        sys.exit(1)

    print(lookup(sys.argv[1]))

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
    "core" : 0,
    "production": 1,
    
    "development": 250,
    "test": 255,
}

# Name of the VPC, Name of the Subnet and the Subnet's Subnet number (must fit within VPC_CIDR to SUBNET_CIDR) for all Subnets
SUBNETS = {
    ("core", "private") : 0,
    ("core", "public") : 1,
    
    ("production", "a") : 0,
    ("production", "b") : 1,
    
    ("development", "pryordm1") : 1,
    
    ("test", "internal") : 0,
    ("test", "external") : 1,
    ("test", "a") : 2,
    ("test", "b") : 3,
    ("test", "test") : 255,
}

# Static hostname, IP address enteries
STATIC = {
    # All of the core devices are listed here for two reasons
    # 1) because we don't want them named xxxx.(private|public).core.boss
    # 2) we want them included in the host files for every machine
    "bastion.core.boss": "10.0.1.4",
    "vault.core.boss": "10.0.0.5",
    "auth.core.boss": "10.0.0.6",
    
    
    "bastion.test.boss": "10.255.1.4",
    "vault.test.boss": "10.255.0.5",
}


HOSTS = """
# Core Machines
{TLD_IP}.{VPC_IP}.{EXTERNAL_SUBNET}.{BASTION_IP}\tbastion.{VPC}.{TLD} bastion
{TLD_IP}.{VPC_IP}.{INTERNAL_SUBNET}.{VAULT_IP}\tvault.{VPC}.{TLD} vault

# Production Machines
{TLD_IP}.{VPC_IP}.{EXTERNAL_SUBNET}.{API_IP}\tapi.{VPC}.{TLD} api
"""



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
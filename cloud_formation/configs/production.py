#!/usr/bin/env python3

# Devices that all VPCs/Subnets may potentially have and Subnet number (must fit under SUBNET_CIDR)
# Subnet number can be a single number or a list of numbers
DEVICES = {
    "bastion": 1,
    "vault": 2,
    "auth": 3,
    "api": 4,
    "web": range(10, 20),
    "db": range(20, 30),
}
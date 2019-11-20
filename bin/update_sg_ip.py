#!/usr/bin/env python3

# Copyright 2019 The Johns Hopkins University Applied Physics Laboratory
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

from requests import get

import alter_path
from lib import aws
from lib import configuration

def get_ip():
    return get('https://api.ipify.org').text + '/32'

class SecurityGroup(object):
    def __init__(self, bosslet_config):
        self.bosslet_config = bosslet_config
        self.client = bosslet_config.session.client('ec2')

        self.vpc_id = None
        self.sg_id = None
        self.ingress = {}

    def load(self, vpc_name, sg_name):
        resp = self.client.describe_vpcs(Filters=[{'Name': 'tag:Name', 'Values': [vpc_name]}])
        self.vpc_id = resp['Vpcs'][0]['VpcId']

        resp = self.client.describe_security_groups(Filters=[{'Name': 'vpc-id', 'Values': [self.vpc_id]},
                                                             {'Name': 'group-name', 'Values': [sg_name]}])

        for sg in resp['SecurityGroups']:
            self.sg_id = sg['GroupId']
            for perms in sg['IpPermissions']:
                if perms['FromPort'] == 22 and perms['ToPort'] == 22 and perms['IpProtocol'] == 'tcp':
                    for perm in perms['IpRanges']:
                        self.ingress[perm['Description']] = perm['CidrIp']

    def remove_ingress(self, name):
        if name not in self.ingress:
            return

        resp = self.client.revoke_security_group_ingress(IpPermissions = [{
                                                             'FromPort': 22, 'ToPort': 22, 'IpProtocol': 'tcp',
                                                             'IpRanges': [{'CidrIp': self.ingress[name], 'Description': name}],
                                                             }],
                                                         GroupId = self.sg_id)

        del self.ingress[name]

    def add_ingress(self, name, cidr):
        if name in self.ingress:
            self.remove_ingress(name)

        resp = self.client.authorize_security_group_ingress(IpPermissions = [{
                                                                'FromPort': 22, 'ToPort': 22, 'IpProtocol': 'tcp',
                                                                'IpRanges': [{'CidrIp': cidr, 'Description': name}],
                                                                }],
                                                            GroupId = self.sg_id)

        self.ingress[name] = cidr

if __name__ == '__main__':
    parser = configuration.BossParser(description = 'Script to update the Security Group with your current IP address')
    parser.add_bosslet()
    parser.add_argument('--vpc',
                        default = 'Test-VPC',
                        help = 'The name of the VPC in which the SG resides')
    parser.add_argument('--sg',
                        default = 'SSH From Home',
                        help = 'The name of the SG to work with')
    parser.add_argument('--list',
                        action = 'store_true',
                        help = 'List currently configured ingress rules')
    parser.add_argument('--rm',
                        action = 'store_true',
                        help = 'Remove the given ingress rule')
    parser.add_argument('name',
                        help = 'The unique name for the SG entry for your address')

    args = parser.parse_args()

    sg = SecurityGroup(args.bosslet_config)
    sg.load(args.vpc, args.sg)

    if args.list:
        print("Ingress SSH rules for '{}' security group".format(args.sg))
        for name, cidr in sg.ingress.items():
            print("\t{}: {}".format(name, cidr))
    elif args.rm:
        sg.remove_ingress(args.name)
    else:
        sg.add_ingress(args.name, get_ip())


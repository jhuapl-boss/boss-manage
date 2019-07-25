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

"""
Script for searching for AWS resources that can be removed.
 * Search for Packer resources that are not cleanned up correctly
 * Search for old AMIs that are no longer used
"""

import re
import os
import argparse

import alter_path
from lib import configuration
from lib import console

def items(d):
    ks = list(d.keys())
    ks.sort()
    for k in ks:
        yield k, d[k]

def get_name(tags):
    for tag in tags:
        if tag['Key'] == 'Name':
            return tag['Value']
    return None

exclude_regex = []
def is_excluded(resource):
    for regex in exclude_regex:
        if regex.match(resource):
            return True
    return False


if __name__ == '__main__':
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    parser = configuration.BossParser(description="This script is used to cleanup AWS resources that were not " + \
                                                  "automatically cleanned up.",
                                      formatter_class=argparse.RawDescriptionHelpFormatter,
                                      epilog='one time setup for new AWS Account')
    parser.add_bosslet()
    parser.add_argument('--exclude', '-e',
                        action = 'append',
                        help = 'Whitelist the given resource(s) from being deleted (supports regex)')
    parser.add_argument('--delete',
                        action = 'store_true',
                        help = 'Delete the indicated resources')
    parser.add_argument('--quiet', '-q',
                        action = 'store_true',
                        help = 'Suppress warnings')
    parser.add_argument('resource',
                        choices = ['ec2', 'sg', 'keypair', 'ami'],
                        help = 'The AWS resource to cleanup')

    args = parser.parse_args()

    if args.exclude:
        for exclude in args.exclude:
            if exclude[0] != '^':
                exclude = '^.*' + exclude
            if exclude[-1] != '$':
                exclude += '.*$'
            exclude_regex.append(re.compile(exclude))

    if args.resource == 'ec2':
        client = args.bosslet_config.session.client('ec2')

        running = {}
        stopped = {}
        unlabled = []

        kwargs = {}
        while kwargs.get('NextToken', '') is not None:
            resp = client.describe_instances(**kwargs)
            for res in resp['Reservations']:
                for inst in res['Instances']:
                    name = get_name(inst.get('Tags', []))
                    state = inst['State']['Name']
                    if name is None:
                        unlabled.append(inst)
                    elif is_excluded(name):
                        pass
                    elif state == 'stopped':
                        stopped[name] = inst
                    elif state == 'running':
                        running[name] = inst
            kwargs['NextToken'] = resp.get('NextToken')

        if len(running) == 0:
            console.info("No unexpected running EC2 instances exist")

        if not args.quiet:
            for inst in unlabled:
                console.warning('Instance {} is not labeled'.format(inst['InstanceId']))
            for name, inst in items(stopped):
                console.warning('Instance {} ({}) is stopped'.format(inst['InstanceId'], name))
        if args.delete:
            for name, inst in items(running):
                console.debug('Deleting EC2 instance {} ({})'.format(inst['InstanceId'], name))
            if console.confirm('Are you sure', default = False):
                for inst in running.values():
                    client.terminate_instances(InstanceIds = [inst['InstanceId']])
        else:
            for name, inst in items(running):
                console.debug('Instance {} ({})'.format(inst['InstanceId'], name))
    elif args.resource == 'sg':
        client = args.bosslet_config.session.client('ec2')

        packer_sgs = []
        launch_sgs = []

        kwargs = {}
        while kwargs.get('NextToken', '') is not None:
            resp = client.describe_security_groups(**kwargs)
            for sg in resp['SecurityGroups']:
                name = sg['GroupName']
                if is_excluded(name):
                    pass
                elif name.startswith('packer ') or \
                     name.startswith('packer_'):
                    packer_sgs.append(sg)
                elif name.startswith('launch-wizard-'):
                    launch_sgs.append(sg)
            kwargs['NextToken'] = resp.get('NextToken')

        if len(packer_sgs) == 0:
            console.info("No Packer Security Groups exist")
        if len(launch_sgs) == 0:
            console.info("No Launch Wizard Security Groups exist")

        if args.delete:
            to_delete = []
            to_delete.extend(packer_sgs)
            to_delete.extend(launch_sgs)
            if len(to_delete) > 0:
                for sg in to_delete:
                    console.debug('Deleting security group: {}'.format(sg['GroupName']))
                if console.confirm('Are you sure', default = False):
                    for sg in to_delete:
                        client.delete_security_group(GroupId = sg['GroupId'])
        else:
            for sg in packer_sgs:
                console.debug('Packer Security Group: {}'.format(sg['GroupName']))
            for sg in launch_sgs:
                console.debug('Launch Wizard Security Group: {}'.format(sg['GroupName']))
    elif args.resource == 'keypair':
        client = args.bosslet_config.session.client('ec2')

        packer_keys = []

        resp = client.describe_key_pairs()
        for kp in resp['KeyPairs']:
            if is_excluded(kp['KeyName']):
                pass
            elif kp['KeyName'].startswith('packer '):
                packer_keys.append(kp)

        if len(packer_keys) == 0:
            console.info("No Packer keypairs exist")
        elif args.delete:
            for kp in packer_keys:
                console.debug('Deleting keypair: {}'.format(kp['KeyName']))
            if console.confirm('Are you sure', default = False):
                for kp in packer_keys:
                    client.delete_key_pair(KeyName = pk['KeyName'])
        else:
            for kp in packer_keys:
                console.debug('Packer keypair: {}'.format(kp['KeyName']))
    elif args.resource == 'ami':
        suffix = args.bosslet_config.AMI_SUFFIX
        client = args.bosslet_config.session.client('ec2')
        resp = client.describe_images(Owners=['self'])
        lookup = {}
        for img in resp['Images']:
            if suffix in img['Name']:
                name, version = img['Name'].split(suffix)
                name += suffix
                if name not in lookup:
                    lookup[name] = []
                lookup[name].append((version, img))
            else:
                if not args.quiet:
                    console.warning('AMI {} is not part of the Boss'.format(img['Name']))

        if len(lookup) == 0:
            console.info("No Boss AMIs exist")
        else:
            all_delete = []
            for key, val in items(lookup):
                hashed = []
                to_delete = []
                for ver, img in val:
                    if ver.startswith('-h'):
                        hashed.append(img)
                    elif ver.startswith('-sprint') or \
                         ver.startswith('-version') or \
                         ver == '': # If there is no version
                        pass
                    else:
                        to_delete.append(img)
                hashed.sort(key = lambda x: x['CreationDate'])
                to_delete.extend(hashed[:-5]) # keep the latest 5 hashed images
                to_delete = [img for img in to_delete if not is_excluded(img['Name'])]
                all_delete.extend(to_delete)

            if args.delete:
                for img in all_delete:
                    console.debug('Deleting AMI: {}'.format(img['Name']))
                if console.confirm('Are you sure', default = False):
                    for img in all_delete:
                        client.deregister_image(ImageId = img['ImageId'])
            else:
                for img in all_delete:
                    console.debug('Boss AMI: {}'.format(img['Name']))
    else:
        print("Not supported")

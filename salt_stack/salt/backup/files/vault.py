# Copyright 2018 The Johns Hopkins University Applied Physics Laboratory
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

# A script to backup and restore data from Vault
# Currently backs up and restores
# * KV data under secret/
# * Vault policies
# * AWS-EC2 Authentication configuration
# * AWS secret backend configuration
#
# NOTE: Restore doesn't restore AWS credentials (the credentials Vault uses to
#       communicate with AWS). Restore expects to restore into a Vault that has
#       already been configured (using lib/vault.py:Vault.configure) so that
#       the different backends are ready for data

from bossutils.vault import Vault
import sys
import os
import json

def export(v, path):
    """Recursive function for exporting all paths and data"""
    # DP NOTE: Taken from lib/vault.py:Vault.export
    if path[-1] != '/':
        path += '/'

    rtn = {}

    results =  v.client.read(path[:-1])
    if results is not None:
        rtn[path[:-1]] = results['data']

    results = v.client.read(path + "?list=true")
    for key in results['data']['keys']:
        key = path + key
        if key[-1] == '/':
            data = export(v, key)
            rtn.update(data)
        else:
            data = v.client.read(key)
            rtn[key] = data['data']

    return rtn

if __name__ == "__main__":
    # usage (backup|restore) domain
    a = sys.argv[1]
    d = sys.argv[2]

    with open("/etc/boss/boss.config", "w") as fh:
        fh.write("""[system]
type = backup

[vault]
url = http://vault.{}:8200
token =
""".format(d))

    v = Vault()

    if a == "backup":
        f = os.path.join(os.environ['OUTPUT1_STAGING_DIR'], 'export.json')
        data = {
            'policies': {},
            'secrets': {},
            'aws-ec2': {},
            'aws': {},
        }

        # Backup policies
        for policy in v.client.list_policies():
            data['policies'][policy] = v.client.read('/sys/policy/' + policy)['rules']

        # Backup secrets
        data['secrets'] = export(v, 'secret/')

        # Backup AWS secret backend roles
        # DP ???: are these now automatically generated for ingest jobs?
        #         if so, should they even be backed up?
        prefix = '/aws/roles'
        for role in v.client.read(prefix + '?list=true')['data']['keys']:
            data['aws'][role] = v.client.read(prefix + '/' + role)['data']['policy']

        # Backup AWS-EC2 auth backend roles
        prefix = '/auth/aws-ec2/role'
        for role in v.client.read(prefix + '?list=true')['data']['keys']:
            d = v.client.read(prefix + '/' + role)['data']

            data['aws-ec2'][role] = {
                    'bound_iam_role_arn': d['bound_iam_role_arn'],
                    'policies': ', '.join(d['policies'])
            }

        with open(f, 'w') as fh:
            json.dump(data, fh, indent=3, sort_keys=True)
    else:
        f = os.path.join(os.environ['INPUT1_STAGING_DIR'], 'export.json')
        with open(f, 'r') as fh:
            data = json.load(fh)

        # DP NOTE: The print statements in the restore are here to help
        #          understand the input data if a call fails to restore

        # Restore policies
        existing = v.client.list_policies()
        for policy in data['policies']:
            if policy in existing:
                existing.remove(policy)

            if policy == 'root':
                # Cannot update root policy
                continue

            print("Restoring policy {}".format(policy))
            v.client.set_policy(policy, data['policies'][policy])

        for policy in existing:
            print("Deleting policy {}".format(policy))
            v.client.delete_policy(policy)

        # Restore secrets
        existing = list(export(v, 'secret/').keys())
        for path in data['secrets']:
            if path in existing:
                existing.remove(path)

            old_data = data['secrets'][path]
            if 'password' in old_data:
                # Don't restore passwords, unless they don't exist
                # A) They haven't changed, so no problem
                # B) They have been changed, and restoring them will
                #    put incorrect data in Vault
                # C) Passwords are restored if they don't exist currently
                #    because Vault data may have been lost and the only
                #    copy of the password is in the backup
                new_data = v.client.read(path)
                if new_data is not None and 'password' in new_data['data']:
                    print("Not restoring {}/password".format(path))
                    old_data['password'] = new_data['data']['password']

            print("Restoring {}".format(path))
            v.write(path, **old_data)

        for path in existing:
            print("Deleting {}".format(path))
            v.delete(path)

        # Backup AWS secret backend roles
        prefix = 'aws/roles'
        existing = v.client.read(prefix + '?list=true')['data']['keys']
        for role in data['aws']:
            if role in existing:
                existing.remove(role)

            print("Restoring aws role {}".format(role))
            v.client.write(prefix + '/' + role, policy = data['aws'][role])

        for role in existing:
            print("Deleting aws role {}".format(role))
            v.client.delete(prefix + '/' + role)

        # Backup AWS-EC2 auth backend roles
        prefix = 'auth/aws-ec2/role'
        existing = v.client.read(prefix + '?list=true')['data']['keys']
        for role in data['aws-ec2']:
            if role in existing:
                existing.remove(role)

            print("Restoring aws-ec2 login {}".format(role))
            v.client.write(prefix + '/' + role, **data['aws-ec2'][role])

        for role in existing:
            print("Deleting aws-ec2 login {}".format(role))
            v.client.delete(prefix + '/' + role)


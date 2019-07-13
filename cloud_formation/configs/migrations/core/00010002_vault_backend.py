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

import json

from lib import aws
from lib import console
from lib import constants as const
from lib.exceptions import BossManageCanceled, BossManageError

def export_path(bosslet_config):
    return const.repo_path('vault', 'private', bosslet_config.names.vault.dns, 'export.json')

def pre_update(bosslet_config):
    # Alert about the change that will happen
    if not console.confirm("This updated will recreate the Vault cluster, proceed?", default = False):
        raise BossManageCanceled()

    # Save the existing data do we can rebuild Vault
    path = export_path(bosslet_config)
    with bosslet_config.call.vault() as vault:
        vault_data = vault.export("secret/")
        with open(path, 'w') as outfile:
            json.dump(vault_data, outfile, indent=3, sort_keys=True)
            print("Vault data exported to {}".format(path))

    # With version 2 the DNS records are now part of the CloudFormation template, so
    # remove the existing DNS record so the update can happen
    console.warning("Removing existing Auth public DNS entry, so CloudFormation can manage the DNS record")
    aws.route53_delete_records(bosslet_config.session,
                               bosslet_config.EXTERNAL_DOMAIN,
                               bosslet_config.names.public_dns('auth'))

def post_update(bosslet_config):
    path = export_path(bosslet_config)

    print("Waiting for Vault...")
    if not bosslet_config.call.check_vault(90, exception=False):
        print("Could not contact Vault, check networking and run the following command")
        print("\tpython3 bastion.py vault.bosslet vault-init")
        print("\tpython3 bastion.py vault.bosslet vault-import {}".format(path))
        print("To verify that Vault is working correctly")
        raise BossManageError("Could not contact Vault")

    aws.route53_delete_records(bosslet_config.session,
                               bosslet_config.INTERNAL_DOMAIN,
                               'consul.' + bosslet_config.INTERNAL_DOMAIN)

    with bosslet_config.call.vault() as vault:
        is_init = False
        try:
            vault.initialize(bosslet_config.ACCOUNT_ID)
            is_init = True
            with open(path, 'r') as infile:
                vault_data = json.load(infile)
                vault.import_(vault_data)
        except Exception as ex:
            print("Problem updating Vault configuration")
            print("Run the following commands to finalize the configuration")
            if not is_init:
                print("\tpython3 bastion.py vault.bosslet vault-init")
            print("\tpython3 bastion.py vault.bosslet vault-import {}".format(path))
            raise

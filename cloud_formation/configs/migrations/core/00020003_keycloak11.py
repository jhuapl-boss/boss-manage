# Copyright 2020 The Johns Hopkins University Applied Physics Laboratory
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from lib.keycloak import KeyCloakClient
from lib import constants as const
import json
import time

def post_update(bosslet_config):
    call = bosslet_config.call
    names = bosslet_config.names

    print(f"Opening realm file at '{const.KEYCLOAK_REALM}'")
    with open(const.KEYCLOAK_REALM, "r") as fh:
        realm = json.load(fh)

    print('Getting Keycloak credentials from Vault')
    with call.vault() as vault:
        auth_data = vault.read(const.VAULT_KEYCLOAK)

    username = 'admin'
    password = auth_data['password']

    # Ensure Keycloak available.
    call.check_keycloak(const.TIMEOUT_KEYCLOAK)

    with call.ssh(names.auth.dns) as ssh:
        print("Restore Keycloak admin user")
        ssh("/srv/keycloak/bin/add-user-keycloak.sh -r master -u {} -p {}".format(username, password))

        print("Restarting Keycloak")
        ssh("sudo service keycloak stop")
        time.sleep(2)
        ssh("sudo killall java") # the daemon command used by the keycloak service doesn't play well with standalone.sh
                                      # make sure the process is actually killed
        time.sleep(3)
        ssh("sudo service keycloak start")

    print("Waiting for Keycloak to restart")
    call.check_keycloak(const.TIMEOUT_KEYCLOAK)

    print('Tunneling to Keycloak server')
    with call.tunnel(names.auth.dns, 8080) as port:
        URL = "http://localhost:{}".format(port)

        with KeyCloakClient(URL, username, password) as kc:
            try:
                scopes = ['email', 'profile']
                print(f'Adding necessary endpoint client scopes for Keycloak 11: {", ".join(scopes)}')
                kc.add_default_client_scopes(realm['realm'], 'endpoint', scopes)
            except Exception:
                print(f'Failed setting client scopes.  Scopes may be set manually via the web console')
                raise

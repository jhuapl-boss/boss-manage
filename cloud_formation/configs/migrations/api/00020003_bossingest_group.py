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
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError

def post_update(bosslet_config):
    # With version 3 the 'bossingest' group should be created
    call = bosslet_config.call
    names = bosslet_config.names

    dns = names.public_dns("api")
    uri = "https://{}".format(dns)

    # Get the bossadmin's credentials
    with call.vault() as vault:
        bossadmin = vault.read("secret/auth/realm")
        auth_uri = vault.read("secret/endpoint/auth")['url']

    # Get the bossadmin's bearer token
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
    }
    params = {
        'grant_type': 'password',
        'client_id': bossadmin['client_id'],
        'username': bossadmin['username'],
        'password': bossadmin['password'],
    }

    auth_uri += '/protocol/openid-connect/token'
    req = Request(auth_uri,
                  headers = headers,
                  data = urlencode(params).encode('utf-8'))
    resp = json.loads(urlopen(req).read().decode('utf-8'))

    # Make an API call that will log the boss admin into the endpoint
    # and create the Large Ingest Group
    call.check_url(uri + '/ping', 60)
    headers = {
        'Authorization': 'Bearer {}'.format(resp['access_token']),
    }
    # NOTE: group name must match value at boss.git/django/bosscore/constants.py:INGEST_GRP
    api_uri = uri + '/latest/groups/bossingest'
    req = Request(api_uri, headers = headers, method='POST')
    try:
        resp = urlopen(req)
        print("Boss Ingest Group: {}".format(resp))
    except HTTPError as ex:
        if ex.code == 404:
            print("Boss Ingest Group already exists")
        else:
            raise

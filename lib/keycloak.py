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

import json
import ssl
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError

from . import exceptions

class KeyCloakClient:
    """Client for connecting to Keycloak and using the REST API.

    Client provides a method for issuing requests to the Keycloak REST API and
    a set of methods to simplify Keycloak configuration.

    Context manager examples:

    kc = KeyCloakClient(url)
    with kc.login(username, password):
        kc.method(arguments)

    with KeyCloakClient(url, username, password) as kc:
        kc.method(arguments)
    """
    def __init__(self, url_base, username=None, password=None, client_id='admin-cli', verify_ssl=True):
        """KeyCloakClient constructor

        Args:
            url_base (string) : The base URL to prepend to all request URLs
            verify_ssl (bool) : Whether or not to verify HTTPS certs
        """
        self.url_base = url_base
        self.token = None
        self.username = username
        self.password = password
        self.client_id = client_id

        if self.url_base.startswith("https") and not verify_ssl:
            self.ctx = ssl.create_default_context()
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE
        else:
            self.ctx = None

    def request(self, url, params=None, headers={}, convert=urlencode, method=None):
        """Make a request to the Keycloak server.

        Args:
            url (string) : REST API URL to query (appended to url_base from constructor)
            params (None|dict) : None or a dict or key values that will be passed
                                 to the convert argument to produce a string
            headers (dict) : Dictionary of HTTP headers
            convert : Function to convert params into a string
                      Defaults to urlencode, taking a dict and making a url encoded string
            method (None|string) : HTTP method to use or None for the default method
                                   based on the different arguments

        Returns:
            (None) : If there is an exception raised
            (dict) : Dictionary containing JSON encoded response
        """
        request = Request(
            self.url_base + url,
            data=None if params is None else convert(params).encode("utf-8"),
            headers=headers,
            method=method
        )

        # DP TODO: rewrite or merge using the boss-tools/bossutils KeycloakClient
        try:
            response = urlopen(request, context=self.ctx).read().decode("utf-8")
            if len(response) > 0:
                response = json.loads(response)
            else:
                response = {}
            return response
        except HTTPError as e:
            raise exceptions.KeyCloakError(e.code, e.reason)

    def login(self, username=None, password=None, client_id=None):
        """Login to the Keycloak master realm and retrieve an access token.

        WARNING: If the base_url is not using HTTPS the password will be submitted
                 in plain text over the network.

        Note: A user must be logged in before any other method calls will work

        The bearer access token is saved as self.token["access_token"]

        An error will be printed if login failed

        Args:
            username (string) : Keycloak username
            password (string) : Keycloak password
            client_id (string) : Keycloak Client ID to authenticate with
        """
        if username is None:
            username = self.username
        if username is None:
            raise Exception("No username set")

        if password is None:
            password = self.password
        if password is None:
            raise Exception("No password set")

        if client_id is None:
            client_id = self.client_id
        if client_id is None:
            raise Exception("No client_id set")

        self.token = self.request(
            "/auth/realms/master/protocol/openid-connect/token",
            params={
                "username": username,
                "password": password,
                "grant_type": "password",
                "client_id": client_id,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )

        if self.token is None:
            #print("Could not authenticate to KeyCloak Server")
            raise exceptions.KeyCloakLoginError(self.url_base, username)

        return self # DP NOTE: So context manager works correctly

    def logout(self):
        """Logout from Keycloak.

        Logout will invalidate the Keycloak session and clean the local token (
        self.token)
        """
        if self.token is None:
            return

        self.request(  # no response
            "/auth/realms/master/protocol/openid-connect/logout",
            params={
                "refresh_token": self.token["refresh_token"],
                "client_id": "admin-cli",
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )

        self.token = None

    def __enter__(self):
        """The start of the context manager, which handles automatically calling logout."""
        if self.token is None:
            self.login()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """The end of the context manager. Print any error when trying to logut and
        propogate any exception that happened while the context was active."""
        try:
            self.logout()
        except:
            print("Error logging out of Keycloak")

        if exc_type is None:
            return None
        else:
            return False # don't supress the exception

    def create_realm(self, realm):
        """Create a new realm based on the JSON based configuration.

            Note: User must be logged into Keycloak first

        Args:
            realm (dict) : JSON dictory configuration for the new realm
        """
        resp = self.request(
            "/auth/admin/realms",
            params=realm,
            headers={
                "Authorization": "Bearer " + self.token["access_token"],
                "Content-Type": "application/json",
            },
            convert=json.dumps
        )

    def get_client(self, realm_name, client_id):
        """Get the realm's client configuration.

            Note: User must be logged into Keycloak first

        Args:
            realm_name (string) : Name of the realm to look in for the client
            client_id (string) : Client ID of client configuration to retrieve

        Returns:
            (None|dict) : None if the client couldn't be located or the JSON
                          dictionary configuration of the client
        """
        resp = self.request(
            "/auth/admin/realms/{}/clients".format(realm_name),
            headers={
                "Authorization": "Bearer " + self.token["access_token"],
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )

        if resp is None:
            return None

        for client in resp:
            if client['clientId'] == client_id:
                return client
        return None

    def update_client(self, realm_name, client):
        """Update the realm's client configuration.

            Note: User must be logged into Keycloak first

        Args:
            realm_name (string) : Name of the realm
            client (dict) : JSON dictory configuration for the updated realm client
        """
        resp = self.request(
            "/auth/admin/realms/{}/clients/{}".format(realm_name, client['id']),
            params=client,
            headers={
                "Authorization": "Bearer " + self.token["access_token"],
                "Content-Type": "application/json",
            },
            convert=json.dumps,
            method="PUT"
        )

    def append_list_properties(self, realm_name, client_id, additions):
        """Append a set of key values to a realm's client configuration.

        Download the current realm's client configuration, updated with the given
        key values, and then upload the updated client configuration to the Keycloak
        server.

            Note: User must be logged into Keycloak first

        Args:
            realm_name (string) : Name of the realm
            client_id (string) : Client ID of client configuration to retrieve
            additions (dict) : dictionary of additions, each entry's key should
                               correspond to a client key and that entry's (singular)
                               value will be appended to the client's property.
        """
        client = self.get_client(realm_name, client_id)

        for key, value in additions.items():
            if key not in client:
                client[key] = []
            if value not in client[key]:
                client[key].append(value)

        self.update_client(realm_name, client)

    def add_redirect_uri(self, realm_name, client_id, uri):
        """Add the given uri as a valid redirectUri to a realm's client configuration.

            Note: User must be logged into Keycloak first

        Args:
            realm_name (string) : Name of the realm
            client_id (string) : Client ID of client configuration to retrieve
            uri (string) : URL to add to the client's list of valid redirect URLs
        """
        self.append_list_properties(realm_name, client_id, {"redirectUris": uri})

    def get_client_installation_url(self, realm_name, client_id):
        """Returns information about this client installation (suitable for wget/curl).

            Note: User must be logged into Keycloak first

        Args:
            realm_name (string) : Name of the realm
            client_id (string) : Client ID of client configuration to retrieve

        Returns:
            (dict) : contains keys
                      * 'url' for the complete URL to retrieve the client installation json
                      * 'headers' for the authorization header populated with the bearer token.
        """
        client = self.get_client(realm_name, client_id)
        installation_endpoint = "{}/auth/admin/realms/{}/clients/{}/installation/providers/keycloak-oidc-keycloak-json"\
            .format(self.url_base, realm_name, client["id"])
        auth_header = "Authorization: Bearer {}".format(self.token["access_token"])
        return {"url": installation_endpoint, "headers": auth_header}


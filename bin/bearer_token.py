#!/usr/bin/env python3

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

"""A script for logging into Keycloak and getting a Bearer access token.

Because the token is backed by a Keycloak session it will expire after a short
period of time (the lifetime of the session before it expires).

The Keycloak token is save to a file called "keycloak.token" in the current directory.

Environmental Variables:
    AWS_CREDENTIALS : File path to a JSON encode file containing the following keys
                      "aws_access_key" and "aws_secret_key"

Author:
    Derek Pryor <Derek.Pryor@jhuapl.edu>
"""

import argparse
import os
import sys
import getpass
import json
import ssl

from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError

import alter_path
from lib import utils

def request(url, params = None, headers = {}, method = None, convert = urlencode):
    """Make an HTTP(S) query and return the results.

        Note: If the url starts with "https" SSL hostname and cert checking is disabled

    Args:
        url (string) : URL to query
        params : None or an object that will be passed to the convert argument
                 to produce a string
        headers (dict) : Dictionary of HTTP headers
        method (None|string) : HTTP method to use or None for the default method
                               based on the different arguments
        convert : Function to convert params into a string
                  Defaults to urlencode, taking a dict and making a url encoded string

    Returns:
        (string) : Data returned from the request. If an error occured, the error
                   is printed and any data returned by the server is returned.
    """
    rq = Request(
        url,
        data = None if params is None else convert(params).encode("utf-8"),
        headers = headers,
        method = method
    )

    if url.startswith("https"):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    else:
        ctx = None

    try:
        response = urlopen(rq, context=ctx).read().decode("utf-8")
        return response
    except HTTPError as e:
        print(e, file=sys.stderr)
        print(e.read().decode("utf-8"), file=sys.stderr)
        return None

if __name__ == "__main__":
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    parser = argparse.ArgumentParser(description = "Script to get a KeyCloak Bearer Token",
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--username", default = None, help = "KeyCloak Username")
    parser.add_argument("--password", default = None, help = "KeyCloak Password")
    parser.add_argument("--output", "-o", default = '-', help = "File to save the token to (default '-' / stdout)")
    parser.add_argument("hostname", help="Pulic hostname of the target Authentication server to get the bearer token for")

    args = parser.parse_args()

    if args.username is None:
        username = input("Username: ")
    else:
        username = args.username

    if args.password is None:
        password = getpass.getpass()
    else:
        password = args.password

    if not args.hostname.lower().startswith("auth"):
        print("Hostname doesn't start with 'auth'", file=sys.stderr)

    url = "https://" + args.hostname + "/auth/realms/BOSS/protocol/openid-connect/token"
    print(url)
    params = {
        "grant_type": "password",
        "client_id": "endpoint",
        "username": username,
        "password": password,
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
    }

    response = request(url, params, headers)
    if response is None:
        sys.exit(1)

    # DP NOTE: Prints are done to stderr so that stdout can be redirected / piped
    #          without capturing status information from the program
    response = json.loads(response)
    if "access_token" not in response:
        print("Didn't get a token, exiting...", file=sys.stderr)
        sys.exit(1)

    token = response["access_token"]
    with utils.open_(args.output, "w") as fh:
        fh.write(token)
        print("Token writen to '{}'".format(args.output), file=sys.stderr)
        sys.exit(0)

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

import argparse
import os
import sys
import json
import ssl
from boto3.session import Session

from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError

def elb_public_lookup(session, hostname):
    """Look up elb public hostname by boss hostname."""
    if session is None: return None

    client = session.client('elb')
    responses = client.describe_load_balancers()

    hostname_ = hostname.replace(".", "-")

    for response in responses["LoadBalancerDescriptions"]:
        if response["LoadBalancerName"].startswith(hostname_):
            return response["DNSName"]
    return None

def create_session(cred_fh):
    """Read the AWS from the given JSON formated file and then create a boto3
    connection to AWS with those credentials.
    """
    credentials = json.load(cred_fh)

    session = Session(aws_access_key_id = credentials["aws_access_key"],
                      aws_secret_access_key = credentials["aws_secret_key"],
                      region_name = 'us-east-1')
    return session

def request(url, params = None, headers = {}, method = None, convert = urlencode):
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
        print(e)
        return e.read().decode("utf-8")

if __name__ == "__main__":
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    parser = argparse.ArgumentParser(description = "Script to get a KeyCloak Bearer Token",
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--aws-credentials", "-a",
                        metavar = "<file>",
                        default = os.environ.get("AWS_CREDENTIALS"),
                        type = argparse.FileType('r'),
                        help = "File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("--token", "-t",
                        metavar = "<token>",
                        default = "keycloak.token",
                        type = argparse.FileType('r'),
                        help = "File with API token (default: keycloak.token)")
    parser.add_argument("--token-type", "-y",
                        metavar = "<token-type>",
                        default = "Bearer",
                        help = "API Token type (default: Bearer)")
    parser.add_argument("--header", "-H",
                        metavar = "<header>",
                        action= "append",
                        help = "HTTP Header(s)")
    parser.add_argument("--method", "-X",
                        choices = ["GET", "POST", "PUT", "DELETE"],
                        default = "GET",
                        metavar = "<method>",
                        help = "HTTP Method (GET|POST|PUT|DELETE)")
    parser.add_argument("--json-data", "-D",
                        metavar = "<json>",
                        help = "JSON Data to send")
    parser.add_argument("--json-file", "-F",
                        metavar = "<file>",
                        type = argparse.FileType('r'),
                        help = "JSON File to send")
    parser.add_argument("domain_name", help="Domain in which to execute the configuration (example: vpc.boss)")
    parser.add_argument("url", default="/ping/", help="Domain in which to execute the configuration (example: vpc.boss)")

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    if args.token is None:
        parser.print_usage()
        print("Error: Token file not provided")
        sys.exit(1)

    session = create_session(args.aws_credentials)
    if args.domain_name.endswith(".boss"):
        hostname = elb_public_lookup(session, "elb." + args.domain_name)
    else:
        hostname = args.domain_name
    token = args.token.read()


    url = "https://" + hostname + args.url
    headers = {}
    headers["Authorization"] = args.token_type + " " + token
    if args.json_data or args.json_file:
        headers["Content-Type"] = "application/json"
        convert = json.dumps

        if args.json_data:
            data = json.loads(args.json_data)
        else:
            data = json.load(args.json_file)
    else:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        convert = urlencode
        data = None

    if args.header:
        for h in args.header:
            k,v = h.split(':')
            headers[h.Trim()] = v.Trim()


    if False:
        print("URL: {}".format(url))
        print("Data: {}".format(data))
        print("Headers: {}".format(headers))
        print("Method: {}".format(args.method))
        print("Converter: {}".format(convert))

    response = request(url, data, headers, args.method, convert)

    #print(response)
    if response is None or len(response) == 0:
        print("No response")
        sys.exit(1)

    max = 130
    try:
        response = json.loads(response)

        print("Response:")
        if type(response) == type([]):
            for val in response:
                print("\t{}".format(val))
        elif type(response) == type({}):
            for key in response:
                val = response[key]
                if type(val) == type(""):
                    if len(val) > max:
                        val = val[:max] + "..."
                print("\t{} -> {}".format(key, val))
        else:
            print("\t{}".format(response))
        print()
    except json.decoder.JSONDecodeError:
        print(response)

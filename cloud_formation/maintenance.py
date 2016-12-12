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

"""
Script to put a stack in and out of maintenance mode.
Script will change the DNS entries for api and auth to point to a static maintenance page.
"""

import argparse
import sys
import os
import boto3
import json
from boto3 import Session
from botocore.exceptions import ClientError
import hosts
import pprint
import library as lib
import datetime

CMDS = ['on', 'off']

def create_help(header, options):
    """Create formated help."""
    return "\n" + header + "\n" + \
           "\n".join(map(lambda x: "  " + x, options)) + "\n"

cmd_help = create_help("options are", CMDS)

MAINTENANCE_BUCKET = "s3-website-us-east-1.amazonaws.com"
CLOUDFRONT = "d3pu2r8smrllig.cloudfront.net"


def migrations_on(session, domain):
    hosted_zone = lib.get_hosted_zone(session)
    (api, auth) = get_api_auth_names(session, domain)
    api_cloud_front = lib.cloudfront_public_lookup(session, api)
    auth_cloud_front = lib.cloudfront_public_lookup(session, auth)
    print("Setting Route53 for: ")
    print("{}: {}".format(api, api_cloud_front))
    print("{}: {}".format(auth, auth_cloud_front))
    lib.set_domain_to_dns_name(session, api, api_cloud_front, hosted_zone)
    lib.set_domain_to_dns_name(session, auth, auth_cloud_front, hosted_zone)


def migrations_off(session, domain):
    hosted_zone = lib.get_hosted_zone(session)
    (api, auth) = get_api_auth_names(session, domain)
    api_elb = lib.elb_public_lookup(session, "elb." + domain)
    auth_elb = lib.elb_public_lookup(session, "auth." + domain)
    print("Setting Route53 for: ")
    print("{}: {}".format(api, api_elb))
    print("{}: {}".format(auth, auth_elb))
    lib.set_domain_to_dns_name(session, api, api_elb, hosted_zone)
    lib.set_domain_to_dns_name(session, auth, auth_elb, hosted_zone)


def get_api_auth_names(session, domain):
    hosted_zone = lib.get_hosted_zone(session)
    if domain in hosts.BASE_DOMAIN_CERTS.keys():
        if hosted_zone != hosts.PROD_DOMAIN:
            print("Incorrect AWS credentials being provided for the production domain, please check them.")
            sys.exit(1)
        api = "api.{}.".format(hosts.BASE_DOMAIN_CERTS[domain])
        auth = "auth.{}.".format(hosts.BASE_DOMAIN_CERTS[domain])
    else:
        print("Maintenance can only be performed in production account.")  # The reason for this is buckets need to be allocated to do this.
        sys.exit(1)
        # if hosted_zone != hosts.DEV_DOMAIN:
        #     print("Possibly wrong credentials being used, domain, {}, is not supposed to be used in this aws account")
        #     sys.exit(1)
        # api = "api-{}.{}.".format(domain.split('.')[0], hosts.DEV_DOMAIN)
        # auth = "auth-{}.{}.".format(domain.split('.')[0], hosts.DEV_DOMAIN)
    return (api, auth)


def create_session(credentials):
    """
    Read the AWS from the credentials dictionary and then create a boto3
    connection to AWS with those credentials.
    Args:
        credentials: AWS credentials in JSON format

    Returns: results boto3 AWS session object

    """
    session = Session(aws_access_key_id=credentials["aws_access_key"],
                      aws_secret_access_key=credentials["aws_secret_key"],
                      region_name='us-east-1')
    return session


def create_parser():
    parser = argparse.ArgumentParser(
        description="",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=cmd_help)
    parser.add_argument("--aws-credentials", "-a",
                        metavar="<file>",
                        default=os.environ.get("AWS_CREDENTIALS"),
                        type=argparse.FileType('r'),
                        help="File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("-yes", "-y",
                        default=False,
                        type=bool,
                        help="Skip, Are you sure? prompt")
    parser.add_argument("cmd",
                        choices=CMDS,
                        help="returns maintenance on or off")
    parser.add_argument("domain_name",
                        help="Domain in which perform maintenance")

    return parser


if __name__ == '__main__':
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    parser = create_parser()
    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    credentials = json.load(args.aws_credentials)
    session = create_session(credentials)

    if args.cmd == "on":
        if not args.yes:
            print("Maintenance mode will update api.")
            print("Are you sure you want to got into maintenance mode")
            resp = input("Update? [N/y] ")
            if len(resp) == 0 or resp[0] not in ('y', 'Y'):
                print("Canceled")
                sys.exit(2)
        migrations_on(session, args.domain_name)
    elif args.cmd == "off":
        migrations_off(session, args.domain_name)

    print("ending script")


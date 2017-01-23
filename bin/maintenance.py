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
Script will change the DNS entries for api to point to a static maintenance page.
"""

import argparse
import sys
import os

import alter_path
from lib import aws
from lib import hosts
from lib.names import AWSNames

CMDS = ['on', 'off']

def create_help(header, options):
    """Create formated help."""
    return "\n" + header + "\n" + \
           "\n".join(map(lambda x: "  " + x, options)) + "\n"

cmd_help = create_help("options are", CMDS)

def warnings(api):
    print("")
    print("It can take up to 10 to 15 minutes for the route53 changes to be seen outside of AWS.")
    print("You can you use: dig {}".format(api))
    print("       This will show either cloudfront or elb server")

def migrations_on(session, domain):
    """
    changes Route53 entry for the api in domain to use cloudfront for the s3 maintenance bucket.
    Args:
        session(Session): boto3 session object
        domain(str): name of domain. Ex: integration.boss

    Returns:
        Nothing
    """
    hosted_zone = aws.get_hosted_zone(session)
    (api, auth) = get_api_auth_names(session, domain)
    api_cloud_front = aws.cloudfront_public_lookup(session, api[:-1])
    print("Setting Route53 for: ")
    print("{}: {}".format(api, api_cloud_front))
    aws.set_domain_to_dns_name(session, api, api_cloud_front, hosted_zone)
    warnings(api)

def migrations_off(session, domain):
    """
    changes Route53 entries for the domain to use the api elastic load balancers
    Args:
        session(Session): boto3 session object
        domain(str): name of domain. Ex: integration.boss

    Returns:
        Nothing
    """
    names = AWSNames(domain)
    hosted_zone = aws.get_hosted_zone(session)
    (api, auth) = get_api_auth_names(session, domain)
    api_elb = aws.elb_public_lookup(session, "elb." + domain)
    print("Setting Route53 for: ")
    print("{}: {}".format(api, api_elb))
    aws.set_domain_to_dns_name(session, api, api_elb, hosted_zone)
    warnings(api)


def get_api_auth_names(session, domain):
    """
    gets the api and auth hostnames from the domain
    Args:
        session(Session): boto3 session object
        domain(str): name of domain. Ex: integration.boss

    Returns:
        tuple(str) of api hostname and auth hostname
    """
    hosted_zone = aws.get_hosted_zone(session)
    if domain in hosts.BASE_DOMAIN_CERTS.keys():
        if hosted_zone != hosts.PROD_DOMAIN:
            print("Incorrect AWS credentials being provided for the production domain, please check them.")
            sys.exit(1)
        api = "api.{}.".format(hosts.BASE_DOMAIN_CERTS[domain])
        auth = "auth.{}.".format(hosts.BASE_DOMAIN_CERTS[domain])
    else:
        print("Maintenance can only be performed in production account.")  # The reason for this is cloudfront sessions would need to be created for dev systems.
        sys.exit(1)
        # if hosted_zone != hosts.DEV_DOMAIN:
        #     print("Possibly wrong credentials being used, domain, {}, is not supposed to be used in this aws account")
        #     sys.exit(1)
        # api = "api-{}.{}.".format(domain.split('.')[0], hosts.DEV_DOMAIN)
        # auth = "auth-{}.{}.".format(domain.split('.')[0], hosts.DEV_DOMAIN)
    return (api, auth)


def create_parser():
    """
    Creates the argumentPaser for the maintenance command.
    Returns:
        (ArgumentParser) not yet parsed.
    """
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

    session = aws.create_session(args.aws_credentials)

    if args.cmd == "on":
        if not args.yes:
            print("Maintenance mode will update the api DNS entry to point to a maintenance page.")
            print("Are you sure you want to go into maintenance mode for {}?".format(args.domain_name))
            resp = input("Update? [N/y] ")
            if len(resp) == 0 or resp[0] not in ('y', 'Y'):
                print("Canceled")
                sys.exit(2)
        migrations_on(session, args.domain_name)
    elif args.cmd == "off":
        migrations_off(session, args.domain_name)


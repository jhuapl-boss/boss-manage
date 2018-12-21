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
from lib import configuration

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

def migrations_on(bosslet_config):
    """
    changes Route53 entry for the api in domain to use cloudfront for the s3 maintenance bucket.
    Args:
        bosslet_config (BossConfiguration): Configuration for the target Bosslet

    Returns:
        Nothing
    """
    (api, _) = get_api_auth_names(bosslet_config)
    api_cloud_front = aws.cloudfront_public_lookup(bosslet_config.session, api[:-1])

    if api_cloud_front is None:
        msg = "Cannot turn on maintenance mode as there is not a Cloudfront site for {}"
        print(msg.format(api[:-1]))
        sys.exit(1)

    print("Setting Route53 for: ")
    print("{}: {}".format(api, api_cloud_front))
    aws.set_domain_to_dns_name(bosslet_config.session,
                               api, api_cloud_front,
                               bosslet_config.EXTERNAL_DOMAIN)

    warnings(api)

def migrations_off(bosslet_config):
    """
    changes Route53 entries for the domain to use the api elastic load balancers
    Args:
        bosslet_config (BossConfiguration): Configuration for the target Bosslet

    Returns:
        Nothing
    """
    (api, _) = get_api_auth_names(bosslet_config)
    api_elb = aws.elb_public_lookup(session, bosslet_config.names.endpoint_elb.dns)

    print("Setting Route53 for: ")
    print("{}: {}".format(api, api_elb))
    aws.set_domain_to_dns_name(bosslet_config.session,
                               api, api_elb,
                               bosslet_config.EXTERNAL_DOMAIN)

    warnings(api)


def get_api_auth_names(bosslet_config):
    """
    gets the api and auth hostnames from the domain
    Args:
        bosslet_config (BossConfiguration): Configuration for the target Bosslet

    Returns:
        tuple(str) of api hostname and auth hostname
    """
    api = bosslet_config.names.public_dns('api') + '.'
    auth = bosslet_config.names.public_dns('auth') + '.'

    return (api, auth)


def create_parser():
    """
    Creates the argumentPaser for the maintenance command.
    Returns:
        (ArgumentParser) not yet parsed.
    """
    parser = configuration.BossParser(description="",
                                      formatter_class=argparse.RawDescriptionHelpFormatter,
                                      epilog=cmd_help)
    parser.add_argument("-yes", "-y",
                        default=False,
                        type=bool,
                        help="Skip, Are you sure? prompt")
    parser.add_argument("cmd",
                        choices=CMDS,
                        help="returns maintenance on or off")
    parser.add_bosslet()

    return parser


if __name__ == '__main__':
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    parser = create_parser()
    args = parser.parse_args()

    if args.cmd == "on":
        if not args.yes:
            print("Maintenance mode will update the api DNS entry to point to a maintenance page.")
            print("Are you sure you want to go into maintenance mode for {}?".format(args.bosslet_name))
            resp = input("Update? [N/y] ")
            if len(resp) == 0 or resp[0] not in ('y', 'Y'):
                print("Canceled")
                sys.exit(2)
        migrations_on(args.bosslet_config)
    elif args.cmd == "off":
        migrations_off(args.bosslet_config)


#!/usr/bin/env python3

import argparse
import os
import sys
import getpass
import json
from boto3.session import Session

import requests

def elb_public_lookup(session, hostname):
    """Lookup the public DNS name for an ELB based on the BOSS hostname.

    Args:
        session (Session) : Active Boto3 session used to lookup ELB
        hostname (string) : Hostname of the desired ELB

    Returns:
        (None|string) : None if the ELB is not located or the public DNS name
    """
    if session is None: return None

    client = session.client('elb')
    responses = client.describe_load_balancers()

    hostname_ = hostname.replace(".", "-")

    for response in responses["LoadBalancerDescriptions"]:
        if response["LoadBalancerName"].startswith(hostname_):
            return response["DNSName"]
    return None

def create_session(cred_fh):
    """Read AWS credentials from the given file object and create a Boto3 session.

        Note: Currently is hardcoded to connect to Region US-East-1

    Args:
        cred_fh (file) : File object of a JSON formated data with the following keys
                         "aws_access_key" and "aws_secret_key"

    Returns:
        (Session) : Boto3 session
    """
    credentials = json.load(cred_fh)

    session = Session(aws_access_key_id = credentials["aws_access_key"],
                      aws_secret_access_key = credentials["aws_secret_key"],
                      region_name = 'us-east-1')
    return session

bearer_token = None
api_hostname = None
url_prefix = "https://{}/v0.5/"
def call_api(method, url_suffix, data = {}):
    url = url_prefix.format(api_hostname) + url_suffix
    print("Calling {} {}".format(method, url))

    headers = { 'Authorization': 'Bearer ' + bearer_token }

    method = method.lower()
    if method == "post":
        headers['Content-Type'] = 'application/json'
        print(data)
        response = requests.post(url, data=json.dumps(data), headers=headers, verify=False)
    elif method == "get":
        response = requests.get(url, headers=headers, verify=False)
    elif method == "delete":
        response = requests.delete(url, headers=headers, verify=False)
    else:
        raise Exception("Unhandled HTTP method {}".format(method))

    #response.raise_for_status()
    print("Status Code: {}".format(response.status_code))
    try:
        print(json.dumps(response.json(), indent=4))
    except:
        print(response.text)

def get_user(user_name = None):
    if user_name is None:
        user_name = input("Username: ")

    call_api("GET", "user/" + user_name)

def add_user(user_name = None, password = None, first_name = None, last_name = None, email = None):
    if user_name is None:
        user_name = input("Username: ")
    if password is None:
        password = getpass.getpass()
    if first_name is None:
        first_name = input("First Name: ")
    if last_name is None:
        last_name = input("Last Name: ")
    if email is None:
        email = input("Email: ")

    data = {
        "password": password,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
    }

    call_api("POST", "user/" + user_name, data = data)

def del_user(user_name = None):
    if user_name is None:
        user_name = input("Username: ")

    call_api("DELETE", "user/" + user_name)

COMMANDS = {
    "get-user": get_user,
    "add-user": add_user,
    "del-user": del_user
}

if __name__ == "__main__":
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    commands = COMMANDS.keys()
    commands_help = create_help("command supports the following:", commands)

    parser = argparse.ArgumentParser(description = "Script to get a KeyCloak Bearer Token",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=commands_help)
    parser.add_argument("--aws-credentials", "-a",
                        metavar = "<file>",
                        default = os.environ.get("AWS_CREDENTIALS"),
                        type = argparse.FileType('r'),
                        help = "File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("--token", "-t",
                        metavar = "<token>",
                        default = "keycloak.token",
                        type = argparse.FileType('r'),
                        help = "KeyCloak Bearer Token file (default: keycloak.token)")
    parser.add_argument("domain_name", help="Domain in which to execute the configuration (example: integration.boss or api.integration.theboss.io)")
    parser.add_argument("command",
                        choices = commands,
                        metavar = "command",
                        help="API Command to execute")
    parser.add_argument("arguments",
                        nargs = "*",
                        help = "Arguments to pass to the command")

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    session = create_session(args.aws_credentials)
    if args.domain_name.endswith(".boss"):
        api_hostname = elb_public_lookup(session, "elb." + args.domain_name)
    else:
        api_hostname = args.domain_name

    bearer_token = args.token.read()

    COMMANDS[args.command.lower()](*args.arguments)

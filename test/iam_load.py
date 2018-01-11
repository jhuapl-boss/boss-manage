#!/usr/bin/env python3

import argparse
import os
import sys
import json
import time


import alter_path
from lib import aws
from lib.vault import Vault
from lib.ssh import vault_tunnel

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = "Script to load test create a large number of IAM credentials using Vault")

    parser.add_argument("--aws-credentials", "-a",
                        metavar = "<file>",
                        default = os.environ.get("AWS_CREDENTIALS"),
                        type = argparse.FileType('r'),
                        help = "File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("--ssh-key", "-s",
                        metavar = "<file>",
                        default = os.environ.get("SSH_KEY"),
                        help = "SSH private key to use when connecting to AWS instances (default: SSH_KEY)")
    parser.add_argument("--load", "-l",
                        metavar = "<load>",
                        default = 50,
                        help = "How many credentials to request from Vault")
    parser.add_argument("domain",
                        metavar = "domain",
                        help = "Domain to target")

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    if args.ssh_key is None:
        parser.print_usage()
        print("Error: SSH key not provided and SSH_KEY is not defined")
        sys.exit(1)

    session = aws.create_session(args.aws_credentials)
    bastion = aws.machine_lookup(session, 'bastion.' + args.domain)
    iam = session.resource('iam')
    client = session.client('iam')

    domain = args.domain.replace('.', '-')

    print("Opening ssh tunnel")
    with vault_tunnel(args.ssh_key, bastion):
        print("\tcomplete")

        v = Vault('vault.' + args.domain)

        #while True:
        #    try:
        #        v.revoke_secret_prefix('aws/creds/ingest-loadtest')
        #    except Exception as ex:
        #        print(ex)
        #
        #    time.sleep(10)
        #sys.exit(0)

        print("Creating IAM policy")
        policy = iam.create_policy(
            PolicyName = '{}-ingest_client-loadtest'.format(domain),
            PolicyDocument = json.dumps({
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": [
                            "iam:ListUsers"
                        ],
                        "Resource": [
                            "*"
                        ]
                    }
                ]
            }),
            Path = '/{}/ingest/'.format(domain),
            Description = 'Vault IAM load test'
        )
        print("\tcomplete")

        try:
            print("Creating Vault AWS role")
            v.write('aws/roles/ingest-loadtest', arn = policy.arn)
            print("\tcomplete")

            try:
                print("Starting test")
                creds = []
                for i in range(int(args.load)):
                    cred = v.read('aws/creds/ingest-loadtest')['data']
                    print(cred)
                    creds.append(cred)

                time.sleep(10)

                for cred in creds:
                    try:
                        c = aws.create_session({'aws_access_key': cred['access_key'],
                                                'aws_secret_key': cred['secret_key']}).client('iam')
                        c.list_users()
                    except Exception as ex:
                        print(ex)

                print("\tcomplete")
            finally:
                try:
                    v.revoke_secret_prefix('aws/creds/ingest-loadtest')
                except Exception as ex:
                    print(ex)

                try:
                    v.delete('aws/roles/ingest-loadtest')
                except Exception as ex:
                    print(ex)
        finally:
            attached = client.list_entities_for_policy(
                PolicyArn = policy.arn,
                EntityFilter = 'User'
            )['PolicyUsers']

            if len(attached) > 0:
                print("Still have attached users")
                for a in attached:
                    try:
                        client.detach_user_policy(UserName = a['UserName'],
                                                  PolicyArn = policy.arn)
                        for key in client.list_access_keys(UserName = a['UserName'])['AccessKeyMetadata']:
                            client.delete_access_key(UserName = a['UserName'],
                                                     AccessKeyId = key['AccessKeyId'])
                        client.delete_user(UserName = a['UserName'])
                    except Exception as ex:
                        print("{}: {}".format(a['UserName'], ex))

            policy.delete()
            

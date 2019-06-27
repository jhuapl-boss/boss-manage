#!/usr/bin/env python3

import argparse
import os
import sys
import json
import time
from boto3.session import Session


import alter_path
from lib.configuration import BossParser

if __name__ == '__main__':
    parser = BossParser(description = "Script to load test create a large number of IAM credentials using Vault")

    parser.add_argument("--load", "-l",
                        metavar = "<load>",
                        default = 50,
                        type = int,
                        help = "How many credentials to request from Vault")
    parser.add_bosslet()

    args = parser.parse_args()
    bosslet_config = args.bosslet_config

    iam = bosslet_config.session.resource('iam')
    client = bosslet_config.session.client('iam')
    domain = bosslet_config.INTERNAL_DOMAIN.replace('.', '-')

    print("Opening ssh tunnel")
    with bosslet_config.call.vault() as v:
        print("\tcomplete")

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
                for i in range(args.load):
                    cred = v.read('aws/creds/ingest-loadtest')
                    print(cred)
                    creds.append(cred)

                time.sleep(10)

                for cred in creds:
                    try:
                        s = Session(aws_access_key_id = cred['access_key'],
                                    aws_secret_access_key = cred['secret_key'])
                        c = s.client('iam')
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
            

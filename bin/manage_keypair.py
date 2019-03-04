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

"""A script to create and delete temporary keypairs.
The scrit will write the keypairs to ~/.ssh/ ande delete them from there accordingly.
Was written primarily to run from within an ec2 instance."""

import argparse
import sys
import os

import alter_path
from lib import aws
from pathlib import Path

if __name__ == '__main__':

    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    actions = ["create", "delete"]
    actions_help = create_help("action supports the following:", actions)

    parser = argparse.ArgumentParser(description = "Script the creation and deletion of keypairs.",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=actions_help)
    parser.add_argument("--aws-credentials", "-a",
                        metavar = "<file>",
                        default = os.environ.get("AWS_CREDENTIALS"),
                        type = argparse.FileType('r'),
                        help = "File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")
    parser.add_argument("action",
                        choices = actions,
                        metavar = "action",
                        help = "Action to execute")
    parser.add_argument("keypairName",
                        metavar = "keypairName",
                        help = "Name of keypair to manage")
    args = parser.parse_args()

    if args.aws_credentials is None:
        try:
            print("AWS credentials not provided and AWS_CREDENTIALS is not defined, assuming IAM role")
            session = aws.use_iam_role()
        except Exception as e:
            parser.print_usage()
            print('Error: Could not assume IAM role')
    else:
        session = aws.create_session(args.aws_credentials)

    client = session.client('ec2')

    #Define key pair path
    key_file_path = Path(str(Path.home()) + '/.ssh/' + str(args.keypairName) + '.pem')

    if args.action == 'create':
        try:
            response = aws.create_keypair(session, args.keypairName)
            print('Protect this keypair and make sure you have access to it.')
        except Exception as e:
            print('Failed to create keypair due to: {}'.format(e))
            response = False

        if response:   
            try:
                key_file_path.touch()
                key_file_path.open('w').write(response['KeyMaterial'])
                print('KeyPair saved in ~/.ssh/')
            except FileExistsError:
                print('Directory {} already existed'.format(key_dir))
                pass

    elif args.action == 'delete':
        response = aws.delete_keypair(session, args.keypairName)
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            try:
                 os.remove(str(key_file_path))
                 print('KeyPair deleted successfully')
            except NameError:
                print('The keypair was deleted from aws but it was not in your .ssh/ directory')
                pass
            except FileNotFoundError:
                print('Could not find the PEM key to delete under ' + str(key_file_path))
                pass
        else:
            print(response['ResponseMetadata'])


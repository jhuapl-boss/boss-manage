#!/usr/bin/env python3

# Copyright 2019 The Johns Hopkins University Applied Physics Laboratory
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

import alter_path
from lib import configuration
from lib import lambdas

class LambdaDownloadCLI(configuration.BossCLI):
    def get_parser(self, ParentParser=configuration.BossParser):
        self.parser = ParentParser(description = "Script for downloading lambda " +
                                   "function code from S3.",
                                   help = 'Download lambda code zip file from S3')
        self.parser.add_bosslet()
        self.parser.add_argument('lambda_name')
        self.parser.add_argument('--save-path', '-p', 
                            default='.',
                            help='Where to save the lambda zip file.')

    def run(self, args):
        return lambdas.download_lambda_zip(args.bosslet_config,
                                           args.lambda_name,
                                           args.save_path)

class LambdaUploadCLI(configuration.BossCLI):
    def get_parser(self, ParentParser=configuration.BossParser):
        self.parser = ParentParser(description = "Script for uploading lambda " +
                                   "function code to S3. To supply arguments " +
                                   "from a file, provide the filename prepended " +
                                   "with an '@'",
                                   help = 'Upload lambda code zip file to S3',
                                   fromfile_prefix_chars = '@')
        self.parser.add_bosslet()
        self.parser.add_argument('zip_name',
                                 help='Name of zip file to upload to S3.')

    def run(self, args):
        return lambdas.upload_lambda_zip(args.bosslet_config,
                                         args.zip_name)

class LambdaBuildCLI(configuration.BossCLI):
    def get_parser(self, ParentParser=configuration.BossParser):
        self.parser = ParentParser(description = "Script for build lambda packages",
                                   help = 'Build lambda packages')
        self.parser.add_bosslet()
        self.parser.add_argument('lambda_name',
                                 help='Name of lambda to build')

    def run(self, args):
        lambdas.load_lambdas_on_s3(args.bosslet_config, args.lambda_name)

class LambdaFreshenCLI(configuration.BossCLI):
    def get_parser(self, ParentParser=configuration.BossParser):
        self.parser = ParentParser(description = "Script for freshening lambda " +
                                   "function code from S3.",
                                   help = 'Refresh Lambda definition with a new code zip')
        self.parser.add_argument('--package',
                                 action='store_true',
                                 help='The lambda_name is the name of the lambda package ' +
                                      'and all lambdas using the package will be updated')
        self.parser.add_bosslet()
        self.parser.add_argument('lambda_name',
                                 help='Name of lambda function to refresh.')

    def run(self, args):
        if args.package:
            lambda_names = [k for k, v in lambdas.package_lookup(args.bosslet_config).items()
                         if v == args.lambda_name]
        else:
            lambda_names = [args.lambda_name]

        for lambda_name in lambda_names:
            lambdas.freshen_lambda(args.bosslet_config, lambda_name)

class LambdaCLI(configuration.NestedBossCLI):
    COMMANDS = {
        'download': LambdaDownloadCLI,
        'upload': LambdaUploadCLI,
        'build': LambdaBuildCLI,
        'freshen': LambdaFreshenCLI,
    }

    PARSER_ARGS = {
        'description': 'Command for working with Boss Lambdas',
    }

    SUBPARSER_ARGS = {
        'dest': 'lambda_method',
        'metavar': 'command',
        'help': 'boss-lambda commands',
    }

if __name__ == '__main__':
    cli = LambdaCLI()
    cli.main()


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

class LambdaFreshenCLI(configuration.BossCLI):
    def get_parser(self, ParentParser=configuration.BossParser):
        self.parser = ParentParser(description = "Script for freshening lambda " +
                                   "function code from S3. To supply arguments " +
                                   "from a file, provide the filename prepended " +
                                   "with an '@'",
                                   help = 'Refresh Lambda definition with a new code zip',
                                   fromfile_prefix_chars = '@')
        self.parser.add_bosslet()
        self.parser.add_argument('lambda_name',
                                 help='Name of lambda function to freshen.')

    def run(self, args):
        return lambdas.freshen_lambda(args.bosslet_config,
                                      args.lambda_name)

class LambdaDownloadCLI(configuration.BossCLI):
    def get_parser(self, ParentParser=configuration.BossParser):
        self.parser = ParentParser(description = "Script for downloading lambda " +
                                   "function code from S3. To supply arguments " +
                                   "from a file, provide the filename prepended " +
                                   "with an '@'",
                                   help = 'Download lambda code zip file from S3',
                                   fromfile_prefix_chars = '@')
        self.parser.add_bosslet()
        self.parser.add_argument('--save-path', '-p', 
                            default='.',
                            help='Where to save the lambda zip file.')

    def run(self, args):
        return lambdas.download_lambda_zip(args.bosslet_config,
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

class LambdaUpdateCLI(configuration.BossCLI):
    def get_parser(self, ParentParser=configuration.BossParser):
        self.parser = ParentParser(description = "Script for updating lambda " +
                                   "function code in S3. To supply arguments " +
                                   "from a file, provide the filename prepended " +
                                   "with an '@'",
                                   help = 'Rebuild and upload the multi-lambda code zip and refresh all lambda definitions',
                                   fromfile_prefix_chars = '@')
        self.parser.add_bosslet()

    def run(self, args):
        lambdas.load_lambdas_on_s3(args.bosslet_config)
        return lambdas.update_lambda_code(args.bosslet_config)

class LambdaBuildCLI(configuration.BossCLI):
    def get_parser(self, ParentParser=configuration.BossParser):
        self.parser = ParentParser(description = "Script for build lambda packages",
                                   help = 'Build lambda packages')
        self.parser.add_bosslet()
        self.parser.add_argument('lambda_name',
                                 help='Name of lambda to build')

    def run(self, args):
        lambdas.build_lambda(args.bosslet_config, args.lambda_name)

class LambdaCLI(configuration.NestedBossCLI):
    COMMANDS = {
        'freshen': LambdaFreshenCLI,
        'download': LambdaDownloadCLI,
        'upload': LambdaUploadCLI,
        'update': LambdaUpdateCLI,
        'build': LambdaBuildCLI,
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


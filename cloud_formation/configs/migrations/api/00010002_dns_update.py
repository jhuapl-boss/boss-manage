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

from lib import aws
from lib import console

def pre_update(bosslet_config):
    # With version 2 the DNS records are now part of the CloudFormation template, so
    # remove the existing DNS record so the update can happen
    console.warning("Removing existing Api public DNS entry, so CloudFormation can manage the DNS record")
    aws.route53_delete_records(bosslet_config.session,
                               bosslet_config.EXTERNAL_DOMAIN,
                               bosslet_config.names.public_dns('api'))


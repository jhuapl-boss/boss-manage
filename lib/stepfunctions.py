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

import os
import sys
from pathlib import Path

from .constants import repo_path

sys.path.append(repo_path('lib', 'heaviside.git'))
import heaviside


class BossStateMachine(heaviside.StateMachine):
    def __init__(self, name, bosslet_config):
        super().__init__(name, session=bosslet_config.session)

        # DP NOTE: Save _translate instead of using super() because it is a lambda
        self.__translate = self._translate
        def _translate(type_, function):
            fqdn = function + '.' + bosslet_config.INTERNAL_DOMAIN
            return self.__translate(type_, fqdn.replace('.', '-'))
        self._translate = _translate

def create(bosslet_config, name, sfn_file, role):
    filepath = repo_path('cloud_formation', 'stepfunctions', sfn_file)
    filepath = Path(filepath)

    machine = BossStateMachine(name, bosslet_config)

    if machine.arn is not None:
        print("StepFunction '{}' already exists, not creating".format(name))
    else:
        machine.create(filepath, role)

def delete(bosslet_config, name):
    machine = BossStateMachine(name, bosslet_config)
    machine.delete()
    # DP ???: remove activity ARNs when deleting the step function or when removing the activity code


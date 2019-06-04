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

class BossVisitor(heaviside.ast.StateVisitor):
    def __init__(self, domain):
        self.domain = domain.replace('.', '-')

    def handle_task(self, task):
        service = task.service.value.lower()
        if service in ('lambda', 'activity'):
            task.arn = task.arn + '-' + self.domain

def create(session, name, domain, sfn_file, role):
    filepath = repo_path('cloud_formation', 'stepfunctions', sfn_file)
    filepath = Path(filepath)

    machine = heaviside.StateMachine(name, session = session)
    machine.add_visitor(BossVisitor(domain))

    if machine.arn is not None:
        print("StepFunction '{}' already exists, not creating".format(name))
    else:
        machine.create(filepath, role)

def delete(session, name):
    machine = heaviside.StateMachine(name, session = session)
    machine.delete()
    # DP ???: remove activity ARNs when deleting the step function or when removing the activity code


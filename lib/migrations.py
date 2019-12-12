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
import importlib
from glob import glob

from . import console
from . import constants as const
from .exceptions import BossManageError

class MigrationFile(object):
    def __init__(self, filepath):
        self.filepath = filepath

        module = filepath.replace(const.repo_path(), '')[1:]
        module = os.path.splitext(module)[0]
        module = module.replace('/', '.')
        self.module_path = module

        filename = module.rsplit('.', 1)[1]
        vers, self.name = filename.split('_', 1)
        self.start, self.stop = int(vers[0:4]), int(vers[4:8])

    def __str__(self):
        return self.module_path

class MigrationManager(object):
    def __init__(self, config, cur_ver, new_ver):
        self.config = config
        self.cur_ver = cur_ver
        self.new_ver = new_ver

        self.pre_cb = None
        self.post_cb = None

        self.load_migrations()

    def check_config_migration_dir(self, dir):
        """
        Checks to see if a migrations directory is already created for a given CF config.  If it is not, it creates it.
        Args:
            dir: config migration directory

        Returns:
        """
        if not os.path.exists(dir):
            os.makedirs(dir, exist_ok=True)

    def load_migrations(self):
        lookup = {}
        config_dir = const.repo_path('cloud_formation', 'configs', 'migrations', self.config)
        self.check_config_migration_dir(config_dir)

        path = const.repo_path('cloud_formation', 'configs', 'migrations', self.config, '*.py')
        for fn in glob(path):
            f = MigrationFile(fn)

            if f.start < self.cur_ver:
                continue
            if f.stop > self.new_ver:
                continue

            lookup[f.start] = f

        self.migrations = []
        cur = self.cur_ver

        try:
            while cur < self.new_ver:
                self.migrations.append(lookup[cur])
                cur = lookup[cur].stop
        except KeyError as ex:
            raise BossManageError("Could not locate migration start at version {}".format(ex))

        if cur != self.new_ver:
            raise BossManageError("Could not locate migration ending at version {}".format(self.new_ver))

        for migration in self.migrations:
            migration.module = importlib.import_module(migration.module_path)

    @property
    def has_migrations(self):
        return len(self.migrations) > 0

    def add_callback(self, pre=None, post=None):
        self.pre_cb = pre
        self.post_cb = post

    def pre_update(self, bosslet_config):
        for migration in self.migrations:
            if hasattr(migration.module, 'pre_update'):
                console.info("Applying {} pre-update migrations".format(migration.name))
                migration.module.pre_update(bosslet_config)

                if self.pre_cb:
                    self.pre_cb(migration)

    def post_update(self, bosslet_config):
        for migration in self.migrations:
            if hasattr(migration.module, 'post_update'):
                console.info("Applying {} post-update migrations".format(migration.name))
                migration.module.post_update(bosslet_config)

                if self.post_cb:
                    self.post_cb(migration)

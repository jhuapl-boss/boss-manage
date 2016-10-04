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

"""
Generate the settings.ini for ndingest after bootup.
"""

import configparser
from spdb.c_lib.ndtype import CUBOIDSIZE

# Location of settings files for ndingest.
NDINGEST_SETTINGS_FOLDER = '/usr/local/lib/python3/site-packages/ndingest/settings'

# Template used for ndingest settings.ini generation.
NDINGEST_SETTINGS_TEMPLATE = NDINGEST_SETTINGS_FOLDER + '/settings.ini.apl'

BOSS_CONFIG = '/etc/boss/boss.config'

def create_settings(tmpl_fp, boss_fp):
    """
    Args:
        tmpl_fp (file-like object): ndingest settings.ini template.
        boss_fp (file-like object): Boss config.
    """
    boss_config = configparser.ConfigParser()
    boss_config.read_file(boss_fp)

    nd_config = configparser.ConfigParser()
    nd_config.read_file(tmpl_fp)

    nd_config['boss']['domain'] = boss_config['system']['fqdn'].split('.', 1)[1]

    nd_config['aws']['tile_bucket'] = boss_config['aws']['tile_bucket']
    nd_config['aws']['cuboid_bucket'] = boss_config['aws']['cuboid_bucket']
    nd_config['aws']['tile_index_table'] = boss_config['aws']['tile-index-table']
    nd_config['aws']['cuboid_index_table'] = boss_config['aws']['s3-index-table']

    nd_config['spdb']['SUPER_CUBOID_SIZE'] = ', '.join(str(x) for x in CUBOIDSIZE[0])

    with open(NDINGEST_SETTINGS_FOLDER + '/settings.ini', 'w') as out:
        nd_config.write(out)

if __name__ == '__main__':
    with open(NDINGEST_SETTINGS_TEMPLATE) as nd_tmpl:
        with open(BOSS_CONFIG) as boss_cfg:
            create_settings(nd_tmpl, boss_cfg)


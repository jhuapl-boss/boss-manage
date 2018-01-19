# Copyright 2018 The Johns Hopkins University Applied Physics Laboratory
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

import sys
import importlib

__LOADED_CONFIGS = {}

def load_config(cf_config):
    if cf_config not in __LOADED_CONFIGS:
        try:
            compose = importlib.import_module("config.boss_compose")
            print("imported config.boss_compose")
        except ImportError:
            try:
                # Use the default for config for every cf_config
                config = importlib.import_module("config.boss_config")
                print("imported config.boss_config")
            except ImportError:
                print("No config/boss_config.py or config/boss_compose.py located")
                print("Cannot load configurations, exiting")
                sys.exit(1) # TODO: raise exception caught by cloudformation.py script
        else:
            default = compose.BOSS_CONFIGS.get("default")
            print("Default compose config: {}".format(default))
            config = compose.BOSS_CONFIGS.get(cf_config, default)
            print("imported config.{}".format(config))
            config = importlib.import_module("config." + config)

        #config.session = aws.create_session(config)
        __LOADED_CONFIGS[cf_config] = config

    return __LOADED_CONFIGS[cf_config]


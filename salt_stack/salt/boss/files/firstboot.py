#!/usr/local/bin/python3

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

### BEGIN INIT INFO
# Provides: boss-firstboot
# Required-Start:
# Required-Stop:
# Default-Start: 2 3 4 5
# Default-Stop:
# Short-Description: boss Python library firstboot script
# Description: Firstboot service script that configures the BOSS Django install
#               to work correctly.
#
### END INIT INFO

import os
import bossutils

bossutils.utils.set_excepthook()
logging = bossutils.logger.BossLogger().logger

def django_initialize():
    logging.info("Create settings.ini for ndingest")
    bossutils.utils.execute("sudo python3 /srv/salt/ndingest/build_settings.py")
    logging.info("Finished creating settings.ini")

    logging.info("Initializing Django")
    migrate_cmd = "sudo python3 /srv/www/django/manage.py "
    bossutils.utils.execute(migrate_cmd + "makemigrations")
    bossutils.utils.execute(migrate_cmd + "makemigrations bosscore")  # will hang if it cannot contact the auth server
    bossutils.utils.execute(migrate_cmd + "makemigrations bossoidc")
    bossutils.utils.execute(migrate_cmd + "makemigrations bossingest")
    bossutils.utils.execute(migrate_cmd + "migrate")
    bossutils.utils.execute(migrate_cmd + "collectstatic --no-input")

    bossutils.utils.execute("sudo service uwsgi-emperor reload")
    bossutils.utils.execute("sudo service nginx restart")
    logging.info("Finished Initializing Django")


if __name__ == '__main__':
    django_initialize()


    # Since the service is to be run once, disable it
    bossutils.utils.stop_firstboot()
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

import bossutils

bossutils.utils.set_excepthook()
bossutils.logger.configure()
logging = bossutils.logger.bossLogger()


def django_initialize():
    logging.info("Initializing Django")
    migrate_cmd = "yes | sudo python3 /srv/www/django/manage.py "
    # Migrations are include in source code
    bossutils.utils.execute(migrate_cmd + "migrate", whole=True, shell=True)
    bossutils.utils.execute(migrate_cmd + "collectstatic --no-input", whole=True, shell=True)

    bossutils.utils.execute("sudo service uwsgi-emperor reload")
    bossutils.utils.execute("sudo service nginx restart")
    logging.info("Finished Initializing Django")

if __name__ == '__main__':
    django_initialize()

    # Since the service is to be run once, disable it
    bossutils.utils.stop_firstboot()

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

    logging.info("Get migration settings from S3")
    mm = bossutils.migration_manager.MigrationManager()
    migration_success = mm.get_migrations()
    if not migration_success:
        logging.info("getting migrations from s3 failed.  Skipping makemigrations, migrate")  # and stopping nginx, uwsgi-emeror"
        #bossutils.utils.execute("sudo service uwsgi-emperor stop")
        #bossutils.utils.execute("sudo service nginx stop")
    else:
        logging.info("Finished getting migration settings")

        logging.info("Initializing Django")
        migrate_cmd = "yes | sudo python3 /srv/www/django/manage.py "
        bossutils.utils.execute(migrate_cmd + "makemigrations", whole=True, shell=True)
        bossutils.utils.execute(migrate_cmd + "makemigrations bosscore", whole=True, shell=True)  # will hang if it cannot contact the auth server
        bossutils.utils.execute(migrate_cmd + "makemigrations bossoidc", whole=True, shell=True)
        bossutils.utils.execute(migrate_cmd + "makemigrations bossingest", whole=True, shell=True)
        bossutils.utils.execute(migrate_cmd + "migrate", whole=True, shell=True)
        bossutils.utils.execute(migrate_cmd + "collectstatic --no-input", whole=True, shell=True)

        bossutils.utils.execute("sudo service uwsgi-emperor reload")
        bossutils.utils.execute("sudo service nginx restart")
        logging.info("Finished Initializing Django")

        logging.info("Put migration settings in S3")
        migration_put_success = mm.put_migrations()
        if not migration_put_success:
            logging.error(
                "At least one migration failed when putting them in s3.")
        else:
            logging.info("Migrations")

if __name__ == '__main__':
    django_initialize()


    # Since the service is to be run once, disable it
    bossutils.utils.stop_firstboot()
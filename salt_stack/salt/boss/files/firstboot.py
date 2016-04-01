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
# Provides: django-firstboot
# Required-Start:
# Required-Stop:
# Default-Start: 2 3 4 5
# Default-Stop:
# Short-Description: Django firstboot script
# Description: Firstboot service script that runs the initial Django configuration commands.
#
### END INIT INFO

# Setup the exception hook to log errors thrown during execution
import os
import bossutils

bossutils.utils.set_excepthook()
logging = bossutils.logger.BossLogger().logger

def configure_django():
    """Run the initial Django configuration commands:
        * manage.py collectstatic
        * manage.py migrate

    to configure serving static files and setup the database.
    """
    file = "/srv/www/manage.py"
    if os.path.exists(file):
        logging.info("manage.py collectstatic")
        bossutils.utils.execute("/usr/local/bin/python3 {} collectstatic --noinput".format(file))

        # May not need to be called if another endpoint has already called this
        logging.info("manage.py migrate")
        bossutils.utils.execute("/usr/local/bin/python3 {} migrate".format(file))

if __name__ == '__main__':
    configure_django()

    # Since the service is to be run once, disable it
    bossutils.utils.stop_firstboot()

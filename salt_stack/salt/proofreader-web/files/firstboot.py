#!/usr/local/bin/python3

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
import traceback
import logging
import sys

logging.basicConfig(filename = "/tmp/proofreader-web.log",
                    filemode = "a",
                    level = logging.DEBUG)

def ex_handler(ex_cls, ex, tb):
    """An exception handler that logs all exceptions."""
    logging.critical(''.join(traceback.format_tb(tb)))
    logging.critical('{0}: {1}'.format(ex_cls, ex))
sys.excepthook = ex_handler
logging.info("Configured sys.excepthook")
### END setting up exception hook

import os
import bossutils

def configure_django():
    """Run the initial Django configuration commands:
        * manage.py collectstatic
        * manage.py migrate

    to configure serving static files and setup the database.
    """
    file = "/srv/www/app/proofreader_apis/manage.py"
    if os.path.exists(file):
        logging.info("manage.py collectstatic")
        bossutils.utils.execute("/usr/local/bin/python3 {} collectstatic --noinput".format(file))

        logging.info("manage.py makemigrations")
        bossutils.utils.execute("/usr/local/bin/python3 {} makemigrations common".format(file))

        logging.info("manage.py migrate")
        bossutils.utils.execute("/usr/local/bin/python3 {} migrate".format(file))

if __name__ == '__main__':
    configure_django()

    # Since the service is to be run once, disable it
    service_name = os.path.basename(sys.argv[0])
    bossutils.utils.execute("update-rc.d -f {} remove".format(service_name))

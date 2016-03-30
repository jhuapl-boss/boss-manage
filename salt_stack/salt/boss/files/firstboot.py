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

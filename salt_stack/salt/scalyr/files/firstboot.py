#!/usr/local/bin/python3

### BEGIN INIT INFO
# Provides: scalyr-firstboot
# Required-Start:
# Required-Stop:
# Default-Start: 2 3 4 5
# Default-Stop:
# Short-Description: Scalyr firstboot script
# Description: Firstboot service script that runs the initial Scalyr configuration commands.
#
### END INIT INFO

# Setup the exception hook to log errors thrown during execution
import traceback
import logging
import sys

logging.basicConfig(filename = "/tmp/boss.log",
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

def configure_scalyr():
    """
    Creates a new config file in /etc/scalyr-agent-2/agent.d that sets the
    serverHost parameter using the vendor provided Python script.
    Note that if the serverHost parameter was ALREADY set in
    /etc/scalyr-agent-2/agent.json or in another config file in
    /etc/scalyr-agent-2/agent.d, results are unpredictable.
    """
    file = "/usr/sbin/scalyr-agent-2-config"
    if os.path.exists(file):
        logging.info("Setting host name for Scalyr.")
        cfg = bossutils.configuration.BossConfig()
        host = cfg["system"]["fqdn"]
        bossutils.utils.execute("{} --set-server-host {}".format(file, host))


if __name__ == '__main__':
    configure_scalyr()

    # Since the service is to be run once, disable it
    service_name = os.path.basename(sys.argv[0])
    bossutils.utils.execute("update-rc.d -f {} remove".format(service_name))

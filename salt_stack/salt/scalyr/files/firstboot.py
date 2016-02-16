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
import os
import bossutils

bossutils.utils.set_excepthook()
logging = bossutils.logger.BossLogger()

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
    bossutils.utils.stop_firstboot()

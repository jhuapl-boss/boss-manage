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
logging = bossutils.logger.BossLogger().logger

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
        returncode = bossutils.utils.execute(
            "{} --set-server-host {}".format(file, host))
        if returncode != 0:
            logging.error("Setting host name failed using {}.".format(file))
    else:
        logging.error(
            "Setting host name for Scalyr failed. {} not found.".format(file))


if __name__ == '__main__':
    configure_scalyr()

    # Since the service is to be run once, disable it
    bossutils.utils.stop_firstboot()

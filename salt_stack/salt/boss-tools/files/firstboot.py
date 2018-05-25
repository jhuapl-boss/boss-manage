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
# Provides: bossutils-firstboot
# Required-Start:
# Required-Stop:
# Default-Start: 2 3 4 5
# Default-Stop:
# Short-Description: bossutils Python library firstboot script
# Description: Firstboot service script that configures bossutils to work correctly.
#
### END INIT INFO

import os
import site
from importlib import reload
import bossutils

bossutils.utils.set_excepthook()
logging = bossutils.logger.BossLogger().logger

def read_vault_token():
    """If the Boss configuration file contains a Vault token, call
    Vault().rotate_token() to read a new token from the cubbyhole."""
    config = bossutils.configuration.BossConfig()
    token = config[bossutils.vault.VAULT_SECTION][bossutils.vault.VAULT_TOKEN_KEY]
    if len(token) > 0:
        vault = bossutils.vault.Vault()
        vault.rotate_token()

def set_hostname():
    """Update the hostname of the machine, by configuring the following
        * updating /etc/hosts to add the current IP address, FQDN, and hostname
        * writing the hostname into /etc/hostname
        * calling 'hostname' to update the hostname of the running system
    """
    logging.info("set_hostname()")
    config = bossutils.configuration.BossConfig()

    with open("/etc/hostname", "r") as fh:
        current_hostname = fh.read().strip()

    fqdn = config["system"]["fqdn"]
    hostname, domain = fqdn.split(".", 1)
    ip = bossutils.utils.read_url(bossutils.utils.METADATA_URL + "local-ipv4")

    # while not needed with Rout53 provided DNS, this allows a machine to still
    # refer to itself as hostname without issue with multiple DNS records for
    # the same hostname entry
    logging.info("Modifying /etc/hosts")
    with open("/etc/hosts", "r+") as fh:
        data = fh.read()

        if current_hostname in data:
            data = data.replace(current_hostname, hostname)
        else:
            data += "\n\n{}\t{} {}\n".format(ip, fqdn, hostname)

        fh.seek(0)
        fh.write(data)
        fh.truncate()

    logging.info("Updating /etc/hostname")
    with open("/etc/hostname", "w") as fh:
        fh.write(hostname)
        fh.truncate()

    logging.info("Calling hostname")
    bossutils.utils.execute("hostname -F /etc/hostname")

    logging.info("Updating /etc/resolvconf/resolv.conf.d/base")
    with open("/etc/resolvconf/resolv.conf.d/base", "a") as fh:
        fh.write("\nsearch {}\n".format(domain))

    logging.info("Regenerating resolv.conf")
    bossutils.utils.execute("resolvconf -u")

if __name__ == '__main__':
    # *** Hack by SH to get oic to version 0.13.0
    os.system('sudo pip install oic==0.13.0')
    reload(site)
    logging.info("CONFIG_FILE = \"{}\"".format(bossutils.configuration.CONFIG_FILE))
    logging.info("Creating /etc/boss (if it does not exist)")
    base_dir = os.path.dirname(bossutils.configuration.CONFIG_FILE)
    os.makedirs(base_dir, exist_ok = True)

    bossutils.configuration.download_and_save()
    #read_vault_token() # Not currently supported when generating access tokens
    set_hostname()


    # Since the service is to be run once, disable it
    bossutils.utils.stop_firstboot()
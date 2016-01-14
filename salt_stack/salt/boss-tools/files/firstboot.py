#!/usr/bin/env python3

### BEGIN INIT INFO
# Provides: boss-firstboot
# Required-Start:
# Required-Stop:
# Default-Start: 2 3 4 5
# Default-Stop:
# Short-Description: BOSS Firstboot
# Description: This file executes during the firstboot of a machine
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
    logging.critical(''.join(traceback.format_tb(tb)))
    logging.critical('{0}: {1}'.format(ex_cls, ex))
sys.excepthook = ex_handler
logging.info("Configured sys.excepthook")
### END setting up exception hook

import os
import bossutils

        
def read_vault_token():
    config = bossutils.configuration.BossConfig()
    token = config[bossutils.vault.VAULT_SECTION][bossutils.vault.VAULT_TOKEN_KEY]
    if len(token) > 0:
        vault = bossutils.vault.Vault()
        vault.rotate_token()
        
def set_hostname():
    logging.info("set_hostname()")
    config = bossutils.configuration.BossConfig()
    
    with open("/etc/hostname", "r") as fh:
        current_hostname = fh.read().strip()
    
    fqdn = config["system"]["fqdn"]
    hostname = fqdn.split(".")[0]
    ip = bossutils.utils.read_url(bossutils.utils.METADATA_URL + "local-ipv4")
    
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
    
if __name__ == '__main__':
    logging.info("CONFIG_FILE = \"{}\"".format(bossutils.configuration.CONFIG_FILE))
    logging.info("Creating /etc/boss (if it does not exist)")
    base_dir = os.path.dirname(bossutils.configuration.CONFIG_FILE)
    os.makedirs(base_dir, exist_ok = True)

    bossutils.configuration.download_and_save()
    #read_vault_token()
    set_hostname()
    
    service_name = os.path.basename(sys.argv[0])
    bossutils.utils.execute("update-rc.d -f {} remove".format(service_name))
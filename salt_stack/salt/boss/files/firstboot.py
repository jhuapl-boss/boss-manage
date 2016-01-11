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
                    filemode = "w",
                    level = logging.DEBUG)

def ex_handler(ex_cls, ex, tb):
    logging.critical(''.join(traceback.format_tb(tb)))
    logging.critical('{0}: {1}'.format(ex_cls, ex))
sys.excepthook = ex_handler
logging.info("Configured sys.excepthook")
### END setting up exception hook
    

import urllib.request
import subprocess
import shlex
import os
import sys
import configparser
from boss_utils import CONFIG_FILE, Vault, BossConfig

def execute(cmd):
    subprocess.call(shlex.split(cmd))

USERDATA_URL = "http://169.254.169.254/latest/user-data"
METADATA_URL = "http://169.254.169.254/latest/meta-data/"

def read_url(url):
    logging.info("read_url({})".format(url))
    return urllib.request.urlopen(url).read().decode("utf-8")

def save_user_data():
    logging.info("save_user_data()")
    user_data = read_url(USERDATA_URL)
    logging.debug(user_data)
    with open(CONFIG_FILE, "w") as fh:
        fh.write(user_data)
        
def read_vault_token():
    config = BossConfig()
    token = config[Vault.VAULT_SECTION][Vault.VAULT_TOKEN_KEY]
    if len(token) > 0:
        vault = Vault()
        new_token = vault.read("/cubbyhole", "token")
        vault.logout()
        
        config = vault.config
        config[Vault.VAULT_SECTION][Vault.VAULT_TOKEN_KEY] = new_token
        with open(CONFIG_FILE, "w") as fh:
            config.write(fh)
        
def set_hostname():
    logging.info("set_hostname()")
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    
    with open("/etc/hostname", "r") as fh:
        current_hostname = fh.read().strip()
    
    fqdn = config["system"]["fqdn"]
    hostname = fqdn.split(".")[0]
    ip = read_url(METADATA_URL + "local-ipv4")
    
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
    execute("hostname -F /etc/hostname")
    
def configure_django():
    file = "/srv/www/manage.py"
    if os.path.exists(file):
        logging.info("manage.py collectstatic")
        execute("python3 {} collectstatic --noinput".format(file))
        
        logging.info("manage.py migrate")
        execute("python3 {} migrate".format(file))
    
if __name__ == '__main__':
    logging.info("CONFIG_FILE = \"{}\"".format(CONFIG_FILE))
    logging.info("Creating /etc/boss (if it does not exist)")
    base_dir = os.path.dirname(CONFIG_FILE)
    os.makedirs(base_dir, exist_ok = True)

    if not os.path.exists(CONFIG_FILE):
        logging.info("/etc/boss/boss.config does not exist, configuring firstboot")
    save_user_data()
    #read_vault_token()
    set_hostname()
    configure_django()
    
    service_name = os.path.basename(sys.argv[0])
    execute("update-rc.d -f {} remove".format(service_name))
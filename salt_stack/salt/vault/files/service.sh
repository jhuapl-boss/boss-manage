#!/bin/sh

### BEGIN INIT INFO
# Provides: vault
# Required-Start:
# Required-Stop:
# Default-Start: 2 3 4 5
# Default-Stop: 0 1 6
# Short-Description: Vault
# Description: This file starts and stops the Vault server
#
### END INIT INFO

# DEBUG NOTE: Add `-o /tmp/vault.log` to the ARGS variable and restart the
#             the service to get a logfile with the stdout/stderr from Vault

# Get IP address from output of command `ip` (should be the interface not named
# `lo`:
#
# lo               UNKNOWN        127.0.0.1/8
# eth0             UP             10.103.5.163/24
#
IP=`ip -4 -br address | grep -v lo | awk '{print substr($3, 1, index($3, "/") - 1)}'`

BOSS_CONFIG=/etc/boss/boss.config

until [ -e $BOSS_CONFIG ]
do
    # Wait for boss.config file to be created.
    sleep 1
done

KEY=`grep kms_key $BOSS_CONFIG | cut -d'=' -f2 | tr -d [:blank:]`
TBL=`grep ddb_table $BOSS_CONFIG | cut -d'=' -f2 | tr -d [:blank:]`
ARGS="-N -n vault -u root -r
      -e VAULT_ADVERTISE_ADDR=http://$IP:8200
      -e VAULT_AWSKMS_SEAL_KEY_ID=$KEY
      -e AWS_DYNAMODB_TABLE=$TBL"

case "$1" in
 start)
   # start the vault server
   echo "Starting Vault on ip: $IP"
   daemon $ARGS -- vault server -config=/etc/vault/vault.cfg
   ;;
 stop)
   daemon $ARGS --stop
   ;;
 restart)
   echo "Restarting Vault on ip: $IP"
   daemon $ARGS --restart
   ;;
 status)
   daemon $ARGS --verbose --running
   ;;
 *)
   echo "Usage: vault {start|stop|restart|status}" >&2
   exit 3
   ;;
esac

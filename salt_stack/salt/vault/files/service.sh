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

IP=`ifconfig eth0 | awk '/inet addr/{print substr($2,6)}'`
KEY=`grep kms_key /etc/boss/boss.config | cut -d'=' -f2 | tr -d [:blank:]`
TBL=`grep ddb_table /etc/boss/boss.config | cut -d'=' -f2 | tr -d [:blank:]`
ARGS="-N -n vault -u root -r
      -e VAULT_ADVERTISE_ADDR=http://$IP:8200
      -e VAULT_AWSKMS_SEAL_KEY_ID=$KEY
      -e AWS_DYNAMODB_TABLE=$TBL"

case "$1" in
 start)
   # start the vault server
   daemon $ARGS -- vault server -config=/etc/vault/vault.cfg
   ;;
 stop)
   daemon $ARGS --stop
   ;;
 restart)
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

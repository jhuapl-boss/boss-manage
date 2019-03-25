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

IP=`ifconfig eth0 | awk '/inet addr/{print substr($2,6)}'`
KEY=`grep /etc/vault/vault.cfg | grep kms_key | cut -d'=' -f2 | tr -d [:blank:]`
ARGS="-N -n vault -u root -r -o /tmp/vault.log -e VAULT_ADVERTISE_ADDR=http://$IP:8200 -e VAULT_AWSKMS_SEAL_KEY_ID=$KEY"

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

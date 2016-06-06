#!/bin/sh

### BEGIN INIT INFO
# Provides: consul
# Required-Start:
# Required-Stop:
# Default-Start: 2 3 4 5
# Default-Stop: 0 1 6
# Short-Description: Consul
# Description: This file starts and stops the Consul server
#
### END INIT INFO

ARGS="-N -n consul -u root -r"

case "$1" in
 start)
   NAME='' # use the last two octects of the IP
   # start the vault server
   daemon $ARGS -- consul agent -server -node=$NAME -data-dir=/srv/consul -syslog -join consul

   # need to add additional DNS CNAME consul to hostname
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
   echo "Usage: consul {start|stop|restart|status}" >&2
   exit 3
   ;;
esac
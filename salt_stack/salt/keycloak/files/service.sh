#!/bin/sh

### BEGIN INIT INFO
# Provides: keycloak
# Required-Start:
# Required-Stop:
# Default-Start: 2 3 4 5
# Default-Stop: 0 1 6
# Short-Description: Keycloak
# Description: This file starts and stops the Keycloak server
#
### END INIT INFO

ARGS="-N -n keycloak -u root -r --output=daemon.info"

case "$1" in
 start)
   # start the keycloak server
   daemon $ARGS -- /srv/keycloak/bin/standalone.sh
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
   echo "Usage: keycloak {start|stop|restart|status}" >&2
   exit 3
   ;;
esac
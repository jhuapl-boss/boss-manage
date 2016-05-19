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

ARGS="-N -n keycloak -u root -r"

# $LAUNCH_JBOSS_IN_BACKGROUND and $JBOSS_PIDFILE may be usefule env vars to define

case "$1" in
 start)
   # start the keycloak server
   DB=`grep ^db /etc/boss/boss.config | cut -d= -f2 | tr -d ' '`
   if [ -z "$DB" ]; then
     CONFIG="standalone.xml"
   else
     CONFIG="standalone-ha.xml"
   fi
   daemon $ARGS -- /srv/keycloak/bin/standalone.sh --server-config=$CONFIG
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
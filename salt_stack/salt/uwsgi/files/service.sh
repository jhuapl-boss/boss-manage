#!/bin/sh

### BEGIN INIT INFO
# Provides: uwsgi-emperor
# Required-Start:
# Required-Stop:
# Default-Start: 2 3 4 5
# Default-Stop: 0 1 6
# Short-Description: uWSGI Emperor
# Description: This file starts and stops the uWSGI Emperor
# 
### END INIT INFO

CONFDIR="/etc/uwsgi/apps-enabled"
LOGFILE="/var/log/uwsgi/emperor.log"
PIDFILE="/var/run/uwsgi/emperor.pid"

case "$1" in
 start)
   # Salt script creating the directry doesn't always seem to work
   D=`dirname $PIDFILE`
   [ -d $D ] || mkdir $D
   uwsgi --emperor $CONFDIR --daemonize $LOGFILE --pidfile $PIDFILE -M
   ;;
 stop)
   uwsgi --stop $PIDFILE
   rm $PIDFILE
   ;;
 reload)
   uwsgi --reload $PIDFILE
   ;;
 status)
   if [ -f $PIDFILE ] ; then
      echo "uWSGI Emperor is running"
   else
      echo "uWSGI Emperor is not running"
   fi
   ;;
 *)
   echo "Usage: $0 {start|stop|reload|status}" >&2
   exit 3
   ;;
esac
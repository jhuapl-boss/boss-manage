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

UWSGI="/usr/local/bin/uwsgi"
CONFDIR="/etc/uwsgi/apps-enabled"
LOGFILE="/var/log/uwsgi/emperor.log"
PIDFILE="/var/run/uwsgi/emperor.pid"

case "$1" in
 start)
   # setup error handling in case there are problems
   # http://serverfault.com/questions/103501/how-can-i-fully-log-all-bash-scripts-actions
   exec 3>&1 4>&2
   trap 'exec 2>&4 1>&3' 0 1 2 3
   exec 1>log.out 2>&1
   
   # Salt script creating the directry doesn't always seem to work
   D=`dirname $PIDFILE`
   [ -d $D ] || mkdir $D
   $UWSGI --emperor $CONFDIR --daemonize $LOGFILE --pidfile $PIDFILE -M
   ;;
 stop)
   $UWSGI --stop $PIDFILE
   rm $PIDFILE
   ;;
 reload)
   $UWSGI --reload $PIDFILE
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
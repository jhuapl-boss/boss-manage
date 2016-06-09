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
   exec 3>&1 4>&2
   trap 'exec 2>&4 1>&3' 0 1 2 3
   exec 1>/tmp/consul.out 2>&1

   PEER="$(/usr/local/bin/python3 /usr/lib/boss/addresses.py)" # returned as an array
   NAME=`ifconfig eth0 | awk '/inet addr/{split(substr($2,6), a, "."); print a[3] a[4]}'`
   BOOTSTRAP=`grep ^cluster /etc/boss/boss.config | cut -d= -f2 | tr -d ' '`

   # Create a config file to enable flags not available as command line options
   cat > /etc/consul/consul.config << EOF
{
    "leave_on_terminate": true,
    "bootstrap_expect": $BOOTSTRAP,
    "data_dir" : "/srv/consul",
    "disable_remote_exec": true,
    "disable_update_check": true,
    "enable_syslog": true,
    "node_name": "$NAME",
    "server": true,
    "start_join": $PEER,
    "addresses": { "http": "0.0.0.0" },
    "ports": { "http": 8500 }
}
EOF

   daemon $ARGS -- consul agent -config-file /etc/consul/consul.config
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
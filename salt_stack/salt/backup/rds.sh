#!/bin/bash

# Usage: ./rds.sh (backup|restore) hostname

set -x

ACTION=$1
HOSTNAME=$2
DOMAIN="`echo $2 | cut -d. -f2-`"

case $HOSTNAME in
    endpoint-db*) PATH="secret/endpoint/django/db" ;;
    auth-db*) PATH="secret/keycloak/db" ;;
    *) echo "Unsupported hostname" >&2 ; exit 1 ;;
esac

/bin/cat > /etc/boss/boss.config << EOF
[system]
type = backup

[vault]
url = http://vault.${DOMAIN}:8200
token =
EOF

/usr/local/bin/python3 ~/creds.py "$PATH" | read USER PASSWORD DATABASE

if [ $ACTION == "backup" ] ; then
    /usr/bin/mysqldump --opt \
              --host $HOSTNAME \
              --user $USER \
              --password=$PASSWORD \
              $DATABASE > ${OUTPUT1_STAGING_DIR}/export.sql
else
    /usr/bin/mysql --host $HOSTNAME \
          --user $USER \
          --password=$PASSWORD \
          $DATABASE < ${INPUT1_STAGING_DIR}/export.sql
fi

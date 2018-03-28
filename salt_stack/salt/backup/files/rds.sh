#!/bin/bash
#
# A shell script to load database information from Vault
# and execute mysqldump (backup) or mysql (restore) to
# maintain the target RDS instance. Designed to be executed
# by AWS Data Pipeline, which will handle moving data
# into and out of the EC2 instance

# Usage: ./rds.sh (backup|restore) hostname.domain.tld

#exec 2>&1
#set -x

ACTION=$1
HOSTNAME=$2

# remove the hostname from the fqdn
DOMAIN="`echo $2 | cut -d. -f2-`"

# figure out the Vault path to extract data from
case $HOSTNAME in
    endpoint-db*) PATH="secret/endpoint/django/db" ;;
    auth-db*) PATH="secret/keycloak/db" ;;
    *) echo "Unsupported hostname" >&2 ; exit 1 ;;
esac

# create a basic boss.config so that bossutils.vault
# can correctly connect to and authenticate to Vault
/bin/cat > /etc/boss/boss.config << EOF
[system]
type = backup

[vault]
url = http://vault.${DOMAIN}:8200
token =
EOF

# get the database information from Vault
CREDS="/usr/local/bin/python3 ${HOME}/creds.py $PATH"
USER="`$CREDS user`"
PASSWORD="`$CREDS password`"
DATABASE="`$CREDS name`"

if [ $ACTION == "backup" ] ; then
    /usr/bin/mysqldump --opt \
              --host $HOSTNAME \
              --user $USER \
              --password="$PASSWORD" \
              $DATABASE > ${OUTPUT1_STAGING_DIR}/export.sql
else
    /usr/bin/mysql --host $HOSTNAME \
          --user $USER \
          --password="$PASSWORD" \
          $DATABASE < ${INPUT1_STAGING_DIR}/export.sql
fi

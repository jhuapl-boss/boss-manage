if [ "$#" -lt 1 ] ; then
    echo "Usage: $0 <521>"
    exit 1
fi

if [ "$1" == "production" ] ; then
    hostname="auth.theboss.io"
else
    hostname="auth-$1.thebossdev.io"
fi

echo "Getting bearer token for $hostname"

./bastion.py vault.$1.boss vault-read secret/auth/realm | ./pq .data.password | ./bearer_token.py $hostname --username bossadmin --password - --out keycloak.token

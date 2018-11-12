if [ "$#" -lt 1 ] ; then
    echo "Usage: $0 <bosslet>"
    exit 1
fi

hostname=`./bosslet_eval.py $1 "bosslet.names.public_dns('auth')"`

echo "Getting bearer token for $hostname"

./bastion.py vault.$1 vault-read secret/auth/realm | ./pq .data.password | ./bearer_token.py $hostname --username bossadmin --password - --out keycloak.token

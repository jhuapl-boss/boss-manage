if [ "$#" -lt 1 ] ; then
    echo "Usage: $0 <521>"
    exit 1
fi

./bastion.py vault.$1.boss vault-read secret/auth/realm | ./pq .data.password | ./bearer_token.py auth-$1.thebossdev.io --username bossadmin --password - --out keycloak.token

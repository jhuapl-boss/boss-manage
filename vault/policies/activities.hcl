# Handle endpoint db credentials
path "secret/endpoint/django/db*" {
    capabilities = ["read"]
}

#####################################################
# For cleaning up ingest temporary roles/credentials.
#####################################################
path "aws/roles/ingest*" {
    capabilities = ["delete"]
}

path "aws/creds/ingest*" {
    capabilities = ["delete"]
}

path "sys/leases/revoke-prefix/aws/creds/ingest*" {
    capabilities = ["sudo", "update"]
}
#####################################################
# End cleaning up ingest temporary roles/credentials.
#####################################################

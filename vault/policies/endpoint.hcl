#
path "auth/token/lookup-self" {
    policy = "read"
}

path "cubbyhole/*" {
    policy = "write"
}

# Handle Endpoint server credentials
path "secret/endpoint/*" {
    policy = "read"
}

# User Management API
path "secret/keycloak" {
    policy = "read"
}

#############################################
# Ingest temporary roles/credentials support.
#############################################
path "aws/roles/ingest*" {
    capabilities = ["create", "update", "delete"]
}

path "aws/creds/ingest*" {
    capabilities = ["create", "read", "update", "delete"]
}
path "sys/renew/aws/creds/ingest*" {
    policy = "write"
}

path "sys/leases/revoke-prefix/aws/creds/ingest*" {
    capabilities = ["sudo", "update"]
}
#################################################
# End ingest temporary roles/credentials support.
#################################################

path "aws/creds/endpoint" {
    policy = "read"
}

path "sys/renew/aws/creds/endpoint/*" {
    policy = "write"
}

path "sys/revoke/aws/creds/endpoint/*" {
    policy = "write"
}

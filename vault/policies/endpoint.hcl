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
    policy = "write"
}

path "aws/creds/ingest*" {
    policy = "write"
}

path "sys/renew/aws/creds/ingest*" {
    policy = "write"
}

path "sys/revoke/aws/creds/ingest*" {
    policy = "write"
}

path "sys/revoke-prefix/aws/creds/ingest*" {
    policy = "sudo"
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

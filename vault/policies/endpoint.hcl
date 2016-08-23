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

path "aws/creds/endpoint" {
    policy = "read"
}

path "sys/renew/aws/creds/endpoint/*" {
    policy = "write"
}

path "sys/revoke/aws/creds/endpoint/*" {
    policy = "write"
}
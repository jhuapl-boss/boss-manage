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

path "aws/creds/endpoint" {
    policy = "read"
}
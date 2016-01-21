#
path "auth/token/lookup-self" {
    policy = "read"
}

# Handle token provisioning
path "auth/token/create" {
    policy = "write"
}

path "auth/token/revoke/" {
    policy = "write"
}

# Handle Endpoint server provisioning
path "secret/endpoint/*" {
    policy = "write"
}

path "secret/proofreader/*" {
    policy = "write"
}
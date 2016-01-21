#
path "auth/token/lookup-self" {
    policy = "read"
}

path "cubbyhole/*" {
    policy = "write"
}

# Handle Proofreader server credentials
path "secret/proofreader/*" {
    policy = "read"
}
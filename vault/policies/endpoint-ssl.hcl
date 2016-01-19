# Endpoint Elastic Loadbalancer SSL
path "auth/token/lookup-self" {
    policy = "read"
}

path "cubbyhole/*" {
    policy = "write"
}

path "/pki/issue/ssl" {
    policy = "write"
}
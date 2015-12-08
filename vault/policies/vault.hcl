path "secret/*" {
    policy = "write"
}

path "cubbyhole/*" {
    policy = "write"
}

path "auth/token/lookup-self" {
    policy = "read"
}
path "auth/app-id/map/user-id/*" {
    policy = "write"
}

path "auth/token/lookup-self" {
    policy = "read"
}
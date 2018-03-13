#
path "auth/token/lookup-self" {
    policy = "read"
}

# Handle Endpoint server credentials
path "secret/endpoint/django/db" {
    policy = "read"
}

# User Management API
path "secret/keycloak/db" {
    policy = "read"
}


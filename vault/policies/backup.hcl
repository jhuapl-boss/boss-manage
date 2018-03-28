#
path "auth/token/lookup-self" {
    policy = "read"
}

# Handle Endpoint server credentials
#path "secret/endpoint/django/db" {
#    policy = "read"
#}

# User Management API
#path "secret/keycloak/db" {
#    policy = "read"
#}

# Backup needs access to everything so it can backup and restore data
# Commented out the other rules, as they override the one below
path "*" {
    policy = "write"
}

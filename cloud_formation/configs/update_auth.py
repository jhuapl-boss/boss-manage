import library as lib

def create(session, domain):
    print("KeyPair to communicating with Vault")
    keypair = lib.keypair_lookup(session)
    call = lib.ExternalCalls(session, keypair, domain)

    def configure_auth(auth_port):
        uri = "https://api.theboss.io"
        call.vault_update("secret/endpoint/auth", public_uri = uri)

        creds = call.vault_read("secret/auth")
        kc = lib.KeyCloakClient("http://localhost:{}".format(auth_port))
        kc.login(creds["username"], creds["password"])
        kc.add_redirect_uri("BOSS","endpoint", uri + "/*")
        kc.logout()
    call.set_ssh_target("auth")
    call.ssh_tunnel(configure_auth, 8080)

    print("Restart Django on the Endpoint Servers")
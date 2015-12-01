Vault
=====

The following are instructions on how to setup a personal test Vault server.
The crypto keys are stored on the machine and Vault is only available over
localhost.

### Installing
Like all HashiCorp's offerings, Vault is a [binary download](https://www.vaultproject.io/downloads.html).
Inside the package is the binary for the Vault Server. Extract it into ~/vault/

To install the [hvac](https://github.com/ianunruh/hvac) Vault library run `pip3 install hvac`

### Configuration
Create the following file as ~/vault/vault.cfg, which sets the location to
store data and where to listen for connections

```
backend "file" {
    path = "~/vault/data"
}

listener "tcp" {
    address = "localhost:8200"
    tls_disable = 1
}
```

### Running the server
This document covers running the Vault server in the foreground. If you want to
run it as a service, take a look at boss-manage/salt_stack/salt/vault/files/service.sh
for a starting point.

From the command line run `./vault server --config=vault.cfg` from ~/vault/

### Initialization
The first time a Vault server is started it needs to be initialized. Every
other time it is started the vault needs to be unsealed to allow access to the
encrypted data. Create the following script (~/vault/startup.py) to handle both
operations and run it each time the Vault server is started.

```python
#!/usr/bin/env python3
import hvac

client = hvac.Client(url="http://localhost:8200")
if not client.is_initialized():
    print("Initializing")
    result = client.initialize(1, 1)

    with open("~/vault/vault_token", "w") as fh:
        fh.write(result["root_token"])
    with open("~/vault/vault_key", "w") as fh:
        fh.write(result["keys"][0])
elif client.is_sealed():
    print("Unsealing")
    with open("~/vault/vault_key", "r") as fh:
        client.unseal(fh.read())
else:
    print("Vault is initialized and unsealed")
```

### Communicating with Vault
Once the Vault server is running and unsealed we can store secrets int it. To
do this we need to authenticate to the server using the *root token* that was
created during initialization. The following python3 code shows connecting to
and working with the local Vault server.

```python
import hvac

with open("~/vault/vault_token", "r") as fh:
        root_token = fh.read()

client = hvac.Client(url="http://localhost:8200", token=root_token)
assert client.is_authenticated()

client.write('secret/foo', baz='bar')
print(client.read('secret/foo'))
client.delete('secret/foo')
```

**Note:** All secrets stored should be stored under "/secret/"  
**Note:** Secrets can be stored at any depth, ex "/secret/foo/bar/boo"  
**Note:** There can be multiple key/value pairs at any depth  
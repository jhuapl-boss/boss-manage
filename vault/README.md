Vault
=====

This directory contains scripts for manipulating and maintaining Vault
instances.


bastion.py
----------
Used to setup a ssh tunnel to an AWS bastion instance, allowing connections
to internal AWS instances (a Vault instance for example). The script has to
different operations. First (command 'ssh') is to form a ssh tunnel to the
bastion host and then launch a ssh session to the internal host. Second
(command 'vault-*') is to form a ssh tunnel to the bastion host and then
call the specified method in vault.py to manipulate a remote Vault instance.

**Note:** <bastion_hostname> and <internal_hostname> are the AWS instance names
          of the machines to connect to. Their IP addresses are located by
          querying AWS for the Public or Private IP of the instance.
          
**Note:** Currently the 'ssh' command only supports connecting to an internal
          instance that uses the same keypair as the bastion instance.


vault.py
--------
Used to manipulate a Vault instance. From actions like initializing the Vault
and storing secret information to printing status information about the Vault.
This can either be called by bastion.py or run as a stand-alone script,
connecting to `http://localhost:8200`.

**Note:** Vault private information is stored and read from `private/`.
          **DO NOT COMMIT THIS INFORMATION TO SOURCE CONTROL**
          
**Note:** The Vault keys are only required to unseal the Vault (after a reboot)

**Note:** The Vault (root) token is required for any (non init/unseal)
          operation. The root token is not required, but a token with the
          needed permissions is required.
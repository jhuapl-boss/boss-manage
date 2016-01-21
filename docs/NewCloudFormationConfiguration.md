Creating a new CloudFormation Configuration
===========================================

Intro
-----
CloudFormation is the AWS service to creating a set of resources altogether,
ensuring that they all get created without problem, and deleting them
altogether. The *cloud_formation/cloudformation.py* script is used to create
different CloudFormation configurations (stacks) and then launch them in AWS.

There are two options, either create a new configuration or update an existing
configuration. Right now there are two primary configurations:

    * *configs/core.py* which creates a new VPC with a Bastion and Vault server
    * *configs/production.py* which expects to be launched into the VPC that
    *configs/core.py* created, creates the rest of the production resources and
    links them to the Vault server previously created.

Creating a new configuration
----------------------------
If creating a new CloudFormation configuration either copy *configs/production.py*
or use it as a reference on how to structure the new configuration. The following
points are important to keep in mind:

    * The *create()* function is called when calling `cloudformation.py create ...`
    * The *generate()* function is called when calling `cloudformation.py generate ...`
    * The *ADDRESSES* dictionary needs to contain the name of new machines so that
    an IP address can be generated for the new machine(s)
        * The value for the dictionary is either a single integer or a *range()*
        * If a *range()* the names <key>, <key>1, <key>2, ... are defined
    * The second argument for the "vault-provision" call is the token policy, this
    is most likely the type of the machine you are creating.
        * Vault policies are restrictive and only allow access to needed resources.
        "Vault Users and Policies.docx" on Confluence describes the known users and
        policies.
        * If a new policy needs to be created, they are located under *vault/policies/*
        * If a new polciy is created, the core configuration needs to be relaunched.
    * To populate credential information in Vault for a launching instance (for
    example Django credentials) you can use the generic "vault-write" command:
    ```
    call_vault("vault-write", "secret/path/to/use", key=value, key1=value1, ...)
    ```
    **Note:* any data stored should be in a location that the provisioned token
    has access to or the VM will not be able to read the secrets.
    * Follow the example of *production.py* with regard to error handling. If
    an exception occurs after provisioning an access token, please revoke it.

Updating an existing configuration
----------------------------------
Updating an existing configuration is similar to creating a new one. Make sure
to work in a branch when updating an existing configuration and only merge when
it is in a working state for others to use.
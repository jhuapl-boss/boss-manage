Boss Manage Utilities
=====

Table of Contents:

* [Connecting from within APL](#Connecting-from-within-APL)
* [Hostnames](#Hostnames)
* [packer.py](#packerpy)
* [bastion.py](#bastionpy)
* [ssh.py](#sshpy)
* [vault.py](#vaultpy)
* [cloudformation.py](#cloudformationpy)
* [sfn-compile.py](#sfn-compile)
* [Scalyr Enviroment Variables](#Scalyr-Enviroment-Variables)
* [create_certificate.py](#create_certificatepy)
* [iam_utils.py](#iam_utilspy)
* [one_time_aws_account_setup.py](#one_time_aws_account_setuppy)
* [scalyr-tool](#scalyr-tool)
* [suspend_termination.py](#suspend_terminationpy)
* [update_lambda_fcn.py](#update_lambda_fcnpy)
* [bearer_token.py](#bearer_tokenpy)
* [bearer_token.sh](#bearer_token.sh)
* [copy_password.sh](#copy_password.sh)
* [pq](#pq)

This directory contains the differe utilities and script for building and
interacting with the BOSS infrastructure.

**Note:** Most scripts will diplay a help message when run without arguments
and the `-h` or `--help` flag can be used to get more detailed help information

Connecting from within APL
--------------------------
The scripts in this directory all support using a bastion / proxy host to
route all non-web traffic through. This information is read automatically
from environment variables.

    * BASTION_IP is the IP address / DNS name of the bastion / proxy host
    * BASTION_KEY is the SSH private key to authenticate with
    * BASTION_USER is the username to log into the host as

The file *set_vars.sh* can be sourced to set these variables,
`source set_vars.sh`

Hostnames
---------
Hostnames are the AWS EC2 instance name of the machine to connect to. The IP
addresses are located by querying AWS for the Public or Private IP of the
instance.

Instances that are part of a AWS Auto Scaling Group there all have the same
name. If you need to connect to a specific instance you can prefix the hostname
with an index (ex 0.auth.integration.boss). The index is zero based (numbering
starts at zero). If you don't specify an index for machines in an Auto Scaling
Group, the first instance is used.

**Note:** Instances are sorted by Instance Id before indexing

packer.py
---------
Used to simplify the building of machine images using [Packer](https://www.packer.io/)
and [SaltStack](http://saltstack.com/). The scrpt tags built AWS AMIs with the commit
version and it can build multiple images at the same time.

Requirements:

* git - Should be installed under $PATH or in the boss-manage.git/bin/ directory
* packer - Should be installed under $PATH or in the boss-manage.git/bin/ directory
* microns bastion private key - Should be in the same directory as the packer binary

Important Arguments:

* `--name` will name the built AMI. By default the first 8 characters of the
  commit hash are used. A name can be something like "production", "integration",
  "test", or your username. If the name "test" is used it also implies that any
  existing AMI with the same name will be deregistered first. (making it easier
  to test builds of a machine)
* `<config>` is the name of a Packer variable file under `packer/variables/` to
  build. Multiple config file names can be given, or "all" will build every file
  in `packer/variables/`

When passing multiple config names to the script, it will build them all in
parallel. The output from each build will be sent to the log file `packer/logs/<config>.log`.

bastion.py
----------
Used to setup a ssh tunnel to an AWS bastion instance, allowing connections
to internal AWS instances (a Vault instance for example). The script has to
different operations.

 * `ssh`: Forms a ssh tunnel to the bastion host and then launches a ssh session
          to the internal host.
 * `scp`: Forms a ssh tunnel to the bastion host and then launches a scp command
          to copy a file from/to the internal machine.
 * `ssh-cmd`: Forms a ssh tunnel to the bastion host and then launches ssh with
              the given command. If no command is given on the command line the
              user will be prompted for the command.
 * `ssh-tunnel`: Forms a ssh tunnel to the bastion host and then a second ssh
                 tunnel to the target machine. The tunnel will be kept up until
                 the user closes it. If the target port and local port are not
                 specified on the command line the user will be prompted for them.
 * `vault-`: Form a ssh tunnel to the bastion host and then call the specified
              method in vault.py to manipulate a remote Vault instance.

**Note:** Currently the ssh commands only supports connecting to an internal
          instance that uses the same keypair as the bastion instance.

**Example:** Logging into Vault via the bastion server.

````bash
./bastion.py vault.<your VPC>.boss ssh
````

ssh.py
------
Similar to bastion.py, this script is used to ssh into an AWS instance
that has a public IP (like the bastion machine of a VPC). It currently
only supports getting a ssh shell or running a single command.

vault.py
--------
Used to manipulate a Vault instance. From actions like initializing the Vault
and storing secret information to printing status information about the Vault.
This can either be called by bastion.py or run as a stand-alone script,
connecting to `http://localhost:3128`.

**Note:** Vault private information is stored and read from `private/`.
          **DO NOT COMMIT THIS INFORMATION TO SOURCE CONTROL**

**Note:** The Vault keys are only required to unseal the Vault (after a reboot)

**Note:** The Vault (root) token is required for any (non init/unseal)
          operation. The root token is not required, but a token with the
          needed permissions is required.

cloudformation.py
-----------------
Used to create and launch the different CloudFormation templates that build up
the BOSS infrastructure. The script tags the resources launched with the commit
version and EC2 instances with the commit version of the AMI used (if the AMI has
one).

Requirements:

* git - Should be installed under $PATH
* pip3 install -r boss-manage.git/requirements.txt
* access to private keys used to launch the core configuration under `~/.ssh/`
* AWS API credentials with IAM privileges required to launch the configurations
  * Look at `docs/InstallGuide.md` for more specifics on IAM permissions required

Important Arguments:

* `--ami-version` selects the specific AMI build name as used by `packer.py`. By
  default this is the last built image tagged with a commit hash, but if the
  partial commit hash or specific name is given that AMI is used.
* `--scenario` selects the deployment scenario (development, production, etc)

sfn-compile.py
-----------------
Compiles a heaviside step function DSL file into the AWS Step Function format.
The result can be manually inspected or uploaded using one of the different
AWS Step Function APIs or console.

## Scalyr Enviroment Variables

Update of the monitor config file on https://www.scalyr.com is one of the final steps of the CloudFormation script.  Scalyr retrieves the CloudWatch StatusCheckFailed metric from AWS.  These environment variables **must** be set for this to succeed:

- scalyr_readconfig_token
- scalyr_writeconfig_token

These tokens can be retrieved (and deleted if necessary) from the Scalyr web site under Settings | API Keys.

Here's a sample script for setting these values:

```bash
#!/bin/bash

export scalyr_readconfig_token='some key string'
export scalyr_writeconfig_token='another key string'
```

Run this script like so:

```bash
source scalyr_vars.sh
```

create_certificate.py
---------------------
Script to create a certificate request in AWS Certificate Manager

iam_utils.py
------------
Script used to update production AWS account IAM roles, policies, instance policies, and groups from
the development AWS account.

one_time_aws_account_setup.py
-----------------------------
Script to perform initial initialization on a new AWS account that will host the BOSS infrastructure.

scalyr-tool
-----------
Command line tool for interacting with Scalyr.

suspend_termination.py
----------------------
Suspend or resume the termination and healthchecks processes of an autoscale group.
Useful when debugging or coding on an ASG instance, so the instance is not automatically
terminated when still in use.

update_lambda_fcn.py
--------------------
Create / Update an AWS lambda function's code in S3. Zip the needed file, upload them
to the lambda build server, build the code, and then upload the results into S3.

Used for lambdas that cannot be directly included in a CloudFormation template.

bearer_token.py
---------------
Query the given Keycloak server and get the user's bearer token.

bearer_token.sh
---------------
Stiches together bastion.py and bearer_token.py to pull the bossadmin's password from
vault and get the user's bearer token.

copy_password.sh
----------------
Script for Mac / Linux that reads a given path from vault and copies the password into
the system clipboard. Reading from vault is done using bastion.py

pq
--
Similar to the command line tool jq, pq takes a string containing a python dictionary
and returns the given item within it. Useful when chaining together commands like in
copy_password.sh

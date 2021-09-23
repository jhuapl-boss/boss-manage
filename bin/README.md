Boss Manage Utilities
=====

Table of Contents:

* [AWS API Keys](#AWS-API-Keys)
* [Hostnames](#Hostnames)
* [boss-config.py](#boss-configpy)
* [boss-status.py](#boss-statuspy)
* [packer.py](#packerpy)
* [bastion.py](#bastionpy)
* [ssh.py](#sshpy)
* [vault.py](#vaultpy)
* [cloudformation.py](#cloudformationpy)
* [bossSwitch.py](#bossSwitchpy)
* [iam_utils.py](#iam_utilspy)
* [boss-account.py](#boss-accountpy)
* [boss-cleanup.py](#boss-cleanuppy)
* [boss-lambda.py](#boss-lambdapy)
* [sfn-compile.py](#sfn-compile)
* [create_certificate.py](#create_certificatepy)
* [scalyr-tool](#scalyr-tool)
* [suspend_termination.py](#suspend_terminationpy)
* [bearer_token.py](#bearer_tokenpy)
* [bearer_token.sh](#bearer_token.sh)
* [copy_password.sh](#copy_password.sh)
* [pq](#pq)

This directory contains the differe utilities and script for building and
interacting with the BOSS infrastructure.

**Note:** Most scripts will diplay a help message when run without arguments
and the `-h` or `--help` flag can be used to get more detailed help information

AWS API Keys
------------
The boss-manage code uses a boto3 profile name for referencing the API keys
to use when connecting to AWS.

If working with multiple AWS accounts (and using multiple profiles names) the
manage_profiles.sh script can be used to prevent unintentional use of an AWS
account. It works by modifying the profile names so that they don't match
the name used in the bosslet config file. The script to apply and unapply
the modification when needed.

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

boss-config.py
--------------
Used to view and verify all of the settings for the given bosslet configuration
file. This can be useful if the configuration file contains generated variables
instead of only hardcoded values.

This script can also be used to print a value based on information in the
bosslet configuration, which is useful when scripting interactions with the
bosslet.

boss-status.py
--------------
Used to query the current status of the bosslet CloudFormation templates. This
will print the currently launched configs and if there has been any drift. (Drift
is the AWS term for if there are differences in the running AWS resources from
what is defined in the CloudFormation template).

If there are drifted resources the script can be used to display information about
what has drifted.

packer.py
---------
Used to simplify the building of machine images using [Packer](https://www.packer.io/)
and [SaltStack](http://saltstack.com/). The scrpt tags built AWS AMIs with the git
commit hash and it can build multiple images at the same time.

Requirements:

* git - Should be installed under $PATH or in the boss-manage.git/bin/ directory
* packer - Should be installed under $PATH or in the boss-manage.git/bin/ directory

Important Arguments:

* `--ami-version` will name the built AMI. By default the first 8 characters of the
  commit hash are used. A name can be something like "production", "integration",
  "test", or your username.
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

```bash
# Example - Logging into the Vault EC2 instance
$ bin/bastion.py vault.<bosslet_config> ssh

# Example - Reasing bossadmin credentials from Vault
$ bin/bastion.py vault.<bosslet_config> vault-read secret/auth/realm
```

ssh.py
------
Similar to bastion.py, this script is used to ssh into an AWS instance
that has a public IP (like the lambda build server).

*Note: This script will still use any `OUTBOUND_BASTION` that is defined
in the bosslet config file.*

vault.py
--------
Used to manipulate a Vault instance. From actions like initializing the Vault
and storing secret information to printing status information about the Vault.
This can either be called by bastion.py or run as a stand-alone script,
connecting to `http://localhost:3128`.

**Note:** Vault private information is stored and read from `vault/private/`.
          **DO NOT COMMIT THIS INFORMATION TO SOURCE CONTROL**

**Note:** The Vault encryption keys are stored in the AWS Key Management Service,
          allowing the Vault to automatically restart if in an unhealthy state.
          The key file under `vault/private/` can be used for specific operations,
          like creating a new root token.

**Note:** The Vault (root) token is required for any (non init/unseal)
          operation. The root token is not required, but a token with the
          needed permissions is required.

cloudformation.py
-----------------
Used to create and launch the different CloudFormation templates that build up
the BOSS infrastructure. The script tags the resources launched with the commit
version and EC2 instances with the commit version of the AMI used (if the AMI has
one).

Important Arguments:

* `--ami-version` selects the specific AMI build name as used by `packer.py`. By
  default this is the last built image tagged with a commit hash, but if the
  partial commit hash or specific name is given that AMI is used.

bossSwitch.py
-------------
Used to turn off the Bosslet's auto scale groups (ASG) EC2 instances. This can be used to minimize the cost of a bosslet if it doesn't need to be used for a period of time.

If the period of time where a bosslet doesn't need to be used is an extended period of time, backing up the bosslet and deleting the stack will allow restoring the bosslet while only incuring the cost of S3 data storage.

iam_utils.py
------------
Used to import and export IAM roles, policies, and groups. Used when setting up a new AWS account to provide all of the needed IAM resources that the bosslet(s) will require.

boss-account.py
---------------
Used to help create initial AWS account resources when setting up a new AWS
account to be ready to launch a Boss instance.

boss-cleanup.py
---------------
Used to help detect and, optionally, delete AWS resources. This includes
resources like old AMIs (built using packer.py).

boss-lambda.py
--------------
A wrapper that combinds the functionality of freshen_lambda.py, get_lambda_zip.py,
update_lambda_fcn.py, upload_lambda_zip.py and provides a single script for
interacting with already deployed lambda functions.

sfn-compile.py
-----------------
Compiles a heaviside step function DSL file into the AWS Step Function format.
The result can be manually inspected or uploaded using one of the different
AWS Step Function APIs or console.

create_certificate.py
---------------------
Script to create a certificate request in AWS Certificate Manager

scalyr-tool
-----------
Command line tool for interacting with Scalyr.

suspend_termination.py
----------------------
Suspend or resume the termination and healthchecks processes of an autoscale group.
Useful when debugging or coding on an ASG instance, so the instance is not automatically
terminated when still in use.

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

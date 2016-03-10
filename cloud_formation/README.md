CloudFormation
==============

This directory contains scripts for creating AWS CloudFormation templates,
creating CloudFormation Stacks, and related helper methods for looking up
data in AWS / manually configuring specific items in AWS.

To configure for running from within APLNIS refer to the *vault/README.md*
"Connecting from within APL" section.

cloudformation.py
-----------------
Used to create and launch the different CloudFormation templates that build up
the BOSS infrastructure. The script tags the resources launched with the commit
version and EC2 instances with the commit version of the AMI used (if the AMI has
one).

Requirements:

* git - Should be installed under $PATH
* pip3 boto3 package
* pip3 hvac package
* access to private keys used to launch the core configuration under `~/.ssh/`
* AWS API credentials with IAM privileges required to launch the configurations
  * Look at `docs/InstallGuide.md` for more specifics on IAM permissions required

Important Arguments:

* `-h` will display a full help message with all arguments
* `--ami-version` selects the specific AMI build name as used by `packer.py`. By
  default this is the last built image, but if the partial commit hash or specific
  name is given that AMI is used.

## Scalyr Enviroment Variables

Update of the monitor config file on https://www.scalyr.com is one of the final steps of the CloudFormation script.  Scalyr retrieves the CloudWatch StatusCheckFailed metric from AWS.  These environment variables **must** be set for this to succeed:

- scalyr_readconfig_token
- scalyr_writeconfig_token

These tokens can be retrieved (and deleted if necessary) from the Scalyr web site under Settings | API Keys.

Here's a sample script for setting these values:

````bash
#!/bin/bash

export scalyr_readconfig_token='some key string'
export scalyr_writeconfig_token='another key string'
````

Run this script like so:

````bash
source scalyr_vars.sh
````

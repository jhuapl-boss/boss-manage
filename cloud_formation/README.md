CloudFormation
==============

This directory contains scripts for creating AWS CloudFormation templates,
creating CloudFormation Stacks, and related helper methods for looking up
data in AWS / manually configuring specific items in AWS.

To configure for running from within APLNIS refer to the *vault/README.md*
"Connecting from within APL" section.

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

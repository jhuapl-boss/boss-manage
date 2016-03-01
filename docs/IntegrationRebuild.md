# Weekly Integration Rebuild Guide

This guide helps walk you through the different steps that need to happen on a
weekly basis to relaunch the integration instance with the latest code.

*Note: This guide assumes that you already have an environment setup and can
successfully launch CloudFormation configurations.*

## Repository Setup

To update the boss-manage.git repository submodules to point to the head of the
integration branches for all of the other repositories you need to run the
following
```shell
$ git checkout integration
$ git pull
$ git submodule update --remote
$ git add salt_stack/salt/boss/files/boss.git
$ git add salt_stack/salt/boss-tools/files/boss-tools.git
$ git add salt_stack/salt/proofreader-web/files/proofread.git
$ git commit -m "Updated submodule references"
$ git push
```

## Rebuilding AMIs

Once the boss-manage.git repository submodules are pointed at the latest
integration code, we need to rebuild the AMIs before we launch them.

### Deregistering existing AMIs
Before new AMIs can be created, the old ones need to be deleted (deregistered)

1. Open a web browser
2. Login to the AWS console and open up the EC2 console
3. Select **AMIs** from the left side menu
4. For *vault.boss*, *endpoint.boss*, *proofreader-web.boss*
  1. Right click on the AMI and select **Deregister**
5. Wait for all of the AMIs to be deleted

### Running Packer
For *vault*, *endpoint*, *proofreader-web* execute the following command
```shell
$ cd packer/
$ packer build -var-file=variables/aws-credentials -var-file=variables/aws-bastion -var-file=variables/<machine-type> -only=amazon-ebs vm.packer
```

*Note: you can run the packer commands in parallel to speed up the process of
creating the AMIs*

## Relaunching Integration Stack

### Deleting existing stacks
Before the new integration instance can be created, the existing CloudFormation
Stacks need to be deleted.

1. Open a web browser
2. Login to the AWS console and open up the CloudFormation console
3. For *LoadbalancerIntegrationBoss*, *ProofreaderIntegrationBoss*,
   *ProductionIntegrationBoss*, *CoreIntegrationBoss*
  1. Right click on the Stack and select *Delete Stack*
  2. Wait for the stack to be deleted

### Vault AWS configuration
For Vault to be able to create AWS credentials (used by the Endpoint) you need a
configuration file located at `boss-manage.git/vault/private/vault_aws_credentials`.
If you don't have this, talk to Derek Pryor to get the AWS API keys for an account.
Once you have the needed API keys:

1. Copy `boss-manage.git/packer/variables/aws-credentials.example` to
`boss-manage.git/vault/private/vault_aws_credentials`
  * You may have to create the directory "private"
2. Open `vault_aws_credentials` in a text editor
3. Copy the access key and secret key that you received into the text editor
4. Save `vault_aws_credentials` and close the text editor

### Environment Setup
The scripts make use of multiple environment variables to manage optional
configuration elements.

```shell
$ cd cloudformation/
$ source ../vault/set_vars.sh
```

### Launching configs

For the *core*, *production*, *proofreader*, and *loadbalancer* configurations
run the following command. You have to wait for each command to finish before
launching the next configuration as they build upon each other.
```shell
$ ./cloudformation.py create integration.boss <config>
```

*Note: When launching some configurations there may be an message about manually
configuring Scalyr monitoring. These instructions skip Scalyr configuration and
you can ignore these instructions.*
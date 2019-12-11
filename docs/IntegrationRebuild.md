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
$ git submodule init
$ git submodule update --remote
$ git add salt_stack/salt/boss/files/boss.git
$ git add salt_stack/salt/boss-tools/files/boss-tools.git
$ git add salt_stack/salt/spdb/files/spdb.git
$ git add salt_stack/salt/ndingest/files/ndingest.git
$ git add salt_stack/salt/ingest-client/files/ingest-client.git
$ git add cloud_formation/lambda/dynamodb-lambda-autoscale
$ git commit -m "Updated submodule references"
$ git push
```

## Rebuilding AMIs

Once the boss-manage.git repository submodules are pointed at the latest
integration code, we need to rebuild the AMIs before we launch them.

## Scalyr Write API Key

Before AMIs can be built, the Scalyr API key needs to be set in the Salt pillar.
Log into https://scalyr.com and click on the account name in the upper right.
Select API Keys from the dropdown.  Copy the `Write Logs` key to the clipboard.
At the time of writing (20Oct2017), there are two `Write Logs` keys.  Use the
bottom-most one.  The first one will be deleted, soon.

In a text editor, create `boss-manage/salt-stack/pillar/scalyr.sls`:

```
#  Scalyr API Key - this file has secret data so isn't part of the repo
scalyr:
  log_key: <paste key here>
```

Paste the key from the clipboard so that it replaces `<paste key here>`


### Running Packer
Make sure that the Packer executable is either in $PATH (you can call it by just
calling packer) or in the `bin/` directory of the boss-manage repository.

```shell
$  bin/packer.py integration.boss all
```

*Note: because the packer.py script is running builds in parallel it is redirecting
the output from each Packer subprocess to `boss-manage.git/packer/logs/<config>.log`. Tailing the logs will allow you to track progress (`tail -f packer/logs/<config>.log`)*

*Note: the packer.py script will name the AMIs with the hash of the current commit
you are building from. Make sure that all changes have been committed (they don't
have to be pushed yet) so that the correct commit hash is used.*

**Note: Because the Packer output is redirected, check the logs and/or the AWS
console to verify the creation of the AMIs.**
```shell
$ grep "artifact" packer/log/*.logs
```

Success looks like this:<br/>
==> Builds finished. The artifacts of successful builds are:
Failure like this:
==> Builds finished but no artifacts were created.

It can beneficial to check the logs before all the AMIs are completed, when
issues do occur, they frequently fail early.  Discovering this allows you to
relauch packer.py in another terminal for the failed AMIs, saving time overall.

## Relaunching Integration Stack

### Deleting existing stacks
Before the new integration instance can be created, the existing CloudFormation
Stacks need to be deleted.

```shell
$ ./cloudformation.py delete integration.boss all
```

*Note: If any fail to delete, try running the delete again. If that doesn't work
you can view the problem through the AWS CloudFormation web console.*

### Launching configs

#### Launching

For the *core*, *redis*, *api*, *cachedb*, *activities*, *cloudwatch*, and
*dynamolambda* configurations run the following command. You have to wait for
each command to finish before launching the next configuration as they build
upon each other. **Only use the *--scenario ha-development* flag** if you are
rebuilding integration.  It is not used if you are following these instructions
to build a developer environment.
```shell
$ ./cloudformation.py create integration.boss --scenario ha-development <config>
```

*Note: You may pass all of the configuration names to one call of `cloudformation.py` and have them be launched in sucession*

*Note: When launching some configurations there may be an message about manually
configuring Scalyr monitoring.  Report this as an potential problem if you
encounter this message.*

*Note: The cloudformation.py script will automatically use the latest created AMIs
that are named with a commit hash. Since you just rebuilt the AMIs they should be
the latest ones.*

*Note: By using the '--scenario production' flag you will be spinning up larger/more
resources than in development mode. Omitting the '--scenerio' flag or setting it to 'development'
will deploy the stack with the minimum set of resources.*

## Get bossadmin password
```shell
cd bin
./bastion.py vault.integration.boss vault-read secret/auth/realm
```
Login to https://api.integration.theboss.io/
Uses bossadmin and the password you now have to sync bossadmin to django

## Manually update the api ELB timeout
Go to EC2 in AWS console
select load balancers on left side
click the checkbox for the loadbalancer to change
under attributes
Set "Idle timeout: 300 seconds"
save and refresh the page

## Run tests
Use the instructions in [Testing.md](Testing.md) to run unit tests and integration tests in the newly rebuilt bosslet.

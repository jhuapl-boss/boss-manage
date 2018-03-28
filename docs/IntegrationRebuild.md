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
$ git add salt_stack/salt/proofreader-web/files/proofread.git
$ git add salt_stack/salt/spdb/files/spdb.git
$ git add salt_stack/salt/ndingest/files/ndingest.git
$ git add salt_stack/salt/ingest-client/files/ingest-client.git
$ git add cloud_formation/lambda/dynamodb-lambda-autoscale
$ git commit -m "Updated submodule references"
$ git push
```

## AWS Credentials File
If you are rebuilding integration in the production account, make sure
your **boss-manage/config/aws_credentials** file contains the production
account keys
your **boss-manage/config/set_var.sh** should have
SSH_KEY=integration-prod-20161009.pem

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

Place `microns-bastion20151117.pem` in the `bin` folder.

```shell
$ cd bin
$  ./packer.py auth vault consul endpoint cachemanager activities
```

*Note: because the packer.py script is running builds in parallel it is redirecting
the output from each Packer subprocess to `boss-manage.git/packer/logs/<config>.log`. Because of
buffering you may not see the file update with every new line. Tailing the log
does seem to work (`tail -f packer/logs/<config>.log`)*

*Note: the packer.py script will name the AMIs with the hash of the current commit
you are building from. Make sure that all changes have been committed (they don't
have to be pushed yet) so that the correct commit hash is used.*

**Note: Because the Packer output is redirected, check the logs and/or the AWS
console to verify the creation of the AMIs.**
```shell
$ grep "artifact" ../packer/log/*.logs
```

Success looks like this:<br/>
==> Builds finished. The artifacts of successful builds are:
Failure like this:
==> Builds finished but no artifacts were created.

It can beneficial to check the logs before all the AMIs are completed, when
issues do occur, they frequently fail early.  Discovering this allows you to
relauch packer.py in another terminal for the failed AMIs, saving time overall.

## Relaunching Integration Stack

### Environment Setup
The scripts make use of multiple environment variables to manage optional
configuration elements. Edit `config/set_vars.sh` and review the variables being
set. Verify that the SSH_KEY being used is the desired one and that it exists under
`~/.ssh/` and is chmoded 0400.

```shell
$ cd bin/
$ source ../config/set_vars.sh
```

Set the environment variables necessary to add Scalyr monitoring of AWS instance
health checks.  The Scalyr values may be obtained from this page:
https://www.scalyr.com/keys

Login information was distributed in an encrypted email.

Here's a sample script for setting these values:

```shell
#!/bin/bash

export scalyr_readconfig_token='some key string'
export scalyr_writeconfig_token='another key string'
```

Create this script and save it (config/set_scalyr_vars.sh) for the next time you do the integration test build.  Run this script like so:

```shell
source ../config/set_scalyr_vars.sh
```

### Deleting existing stacks
Before the new integration instance can be created, the existing CloudFormation
Stacks need to be deleted.

```shell
$ cd bin/
$ source ../config/set_vars.sh

# Deletion of cloudwatch, api, actvities, cachedb, and dynamolambda can probably
# be done in parallel.
$ ./cloudformation.py delete integration.boss dynamolambda
$ ./cloudformation.py delete integration.boss cloudwatch
$ ./cloudformation.py delete integration.boss actvities
$ ./cloudformation.py delete integration.boss cachedb
$ ./cloudformation.py delete integration.boss api
$ ./cloudformation.py delete integration.boss redis
$ ./cloudformation.py delete integration.boss core
```

*Note: If any fail to delete, try running the delete again. If that doesn't work
you can view the problem through the AWS CloudFormation web console.*

### Vault AWS configuration
For Vault to be able to create AWS credentials (used by the Endpoint) you need a
configuration file located at `boss-manage.git/vault/private/vault_aws_credentials`.
If you don't have this, talk to Derek Pryor to get the AWS API keys for an account.
Once you have the needed API keys:

1. Copy `boss-manage.git/config/aws-credentials.example` to
`boss-manage.git/vault/private/vault_aws_credentials`
  * You may have to create the directory "private"
2. Open `vault_aws_credentials` in a text editor
3. Copy the access key and secret key that you received into the text editor
4. Save `vault_aws_credentials` and close the text editor
5. If you are building Integration you'll need to have vault_aws_credentials
for the production account.  It should have aws_account and domain filling in like this:
```
{
    "aws_access_key": "",
    "aws_secret_key": "",
    "aws_account": "451493790433",
    "domain": "theboss.io"
}
```
If you are building a personal developer domain it should have this:
```
{
    "aws_access_key": "",
    "aws_secret_key": "",
    "aws_account": "256215146792",
    "domain": "thebossdev.io"
}
```


### Launching configs

#### dynamolambda Requirements

Building the dynamolambda configuration requires NodeJS.  Install v6.10.x from
https://nodejs.org/en/download

A `dynamo_config.template` file is required in
`boss-manage.git/cloud_formation/configs` to set up the Slack integration.
This file is not under source control and should have been distributed to each
developer.

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
Login to https://api.theboss.io/
Uses bossadmin and the password you now have to sync bossadmin to django

## Manually update the api ELB timeout
Go to EC2 in AWS console
select load balancers on left side
click the checkbox for the loadbalancer to change
under attributes
Set "Idle timeout: 300 seconds"
save and refresh the page

## Run unit tests on Endpoint

If you are following these instructions for your personal development environment, skip the
export RUN_HIGH_MEM_TESTS line.  That line runs 2 tests that need >2.5GB of memory
to run and will fail in your environment

```shell
cd bin
./bastion.py endpoint.integration.boss ssh
export RUN_HIGH_MEM_TESTS=True
cd /srv/www/django
sudo -E python3 manage.py test
```
	output should say Ran 257 tests.

## Integration Tests
After the integration instance is launched the following tests need to be run,
results recorded, and developers notified of any problems.

### Endpoint Integration Tests

#### Test While Logged Onto the Endpoint VM

Again, Skip the RUN_HIGH_MEM_TESTS line below if you are following these instructions for
your personal development environment.  That line runs 2 tests that need >2.5GB
of memory to run and will fail in your environment

```shell
export RUN_HIGH_MEM_TESTS=True
cd /srv/www/django
sudo -E python3 manage.py test -- -c inttest.cfg
```
	output should say 55 Tests OK with 7 skipped tests

##### Test the ndingest library.

```shell
# Manual install for now.  Will likely remove use of pytest in the future.
sudo pip3 install pytest
cd /usr/local/lib/python3/site-packages/ndingest
# Use randomized queue names and prepend 'test_' to bucket/index names.
export NDINGEST_TEST=1
pytest -c test_apl.cfg
```

### Cachemanager Integration Tests

#### Test While Logged Onto the Cachemanager VM

```shell
cd /srv/salt/boss-tools/files/boss-tools.git/cachemgr
sudo nose2
sudo nose2 -c inttest.cfg
```
	there is currently issues with some of the tests not getting setup correctly. cache-DB and cache-state-db need to be manutally set to 1.
	or the tests hang.

#### Test Using Intern From a Client

intern integration tests should be run from your local workstation or a VM
**not** running within the integration VPC.

First ensure intern is current:

```shell
# Clone the repository if you do not already have it.
git clone https://github.com/jhuapl-boss/intern.git

# Otherwise update with `pull`.
# git pull

# Make the repository the current working directory.
cd intern

# Check out the integration branch.
# If there is no current integration branch, use master.
git checkout integration

# Ensure dependencies are current.
sudo pip3 install -r requirements.txt
```

In your browser, open https://api.theboss.io/vX.Y/mgmt/token

Your browser should be redirected to the KeyCloak login page.

Create a new account and return to the token page.

Generate a token.

This token will be copied-pasted into the intern config file.

```shell
mkdir ~/.intern
EDITOR ~/.intern/intern.cfg
```

In your text editor, copy and paste the text config values below. Replace all
all tokens with the token displayed in your browser.

```
[Project Service]
protocol = https
host = api.theboss.io
# Replace with your token.
token = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

[Metadata Service]
protocol = https
host = api.theboss.io
# Replace with your token.
token = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

[Volume Service]
protocol = https
host = api.theboss.io
# Replace with your token.
token = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Additionally, create a copy of `~/.intern/intern.cfg` as `test.cfg` in the intern
repository directory.

##### Setup via the Django Admin Page

In your browser, go to https://api.theboss.io/admin

Login using the bossadmin account created previously (this was created during
the endpoint initialization and unit test step).

Click on `Boss roles`.

Click on `ADD BOSS ROLE`.

Find the user you created and add the `ADMIN` role to that user and save.


##### Run Intern Integration Tests

Finally, open a shell and run the integration tests:

```shell
# Go to the location of your cloned intern repository.
cd intern.git
python3 -m unittest discover -p int_test*
```

Output should say:

```
Ran x tests in x.xxxs.

OK
```

### Automated Tests
To be filled out

### Manual Checks
* https://api.theboss.io/ping/
* https://api.theboss.io/latest/collection/
* Login into Scalyr and verify that the new instances appear on the overview page.
* Also on Scalyr, check the cloudwatch log for the presence of the instance IDs of the endpoint.

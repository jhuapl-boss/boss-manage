# Updating the existing Production stack

This guide helps walk you through the different steps that need to happen 
to update an existing production stack with the latest code.

*Note: This guide assumes that you already have an environment setup and can
successfully launch CloudFormation configurations.*

## Rebuild Integration
This is not a manditory step but it is a good idea to [IntegrationRebuild.md](IntegrationRebuild.md) 
before Tag and merge to verify that everything is working.

## Tag and Merge
Follow the instructions in  [TagAndMerge.md](TagAndMerge.md) to create 
AMIs for sprintXX


## AWS Credentials File
Make sure your:
**boss-manage/config/aws_credentials** file contains the production account keys
**boss-manage/vault/private/vault_aws_credentials** file contains the production vault account keys
**boss-manage/config/set_var.sh** should have SSH_KEY=theboss-prod-20161009.pem


### Scalyr Environment Setup
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


### Updating configs

For the *core*, *api* configurations
run the following command. You have to wait for each command to finish before
launching the next configuration as they build upon each other.  

```shell
$ ./cloudformation.py update integration.boss --scenario production core
```

*Note: The cloudformation.py script will automatically use the latest created AMIs
that are named with a commit hash.  If you want to use specific AMIs use the --ami-version*

After completion check that vault still works, look for password:
./bastion.py bastion.production.boss vault.production.boss vault-read secret/auth/realm

This will show the status of all the consul nodes:
./bastion.py bastion.production.boss consul.production.boss ssh-all 'sudo consul operator raft -list-peers; sudo consul members'

```shell
$ ./cloudformation.py update integration.boss --scenario production api
```

API failed to update.  Here is the error message encountered. 
UPDATE_FAILED    AWS::DynamoDB::Table    tileIndex    CloudFormation cannot update a stack when a 
custom-named resource requires replacing. Rename tileindex.production.boss and update the stack again.


======================================================================
## Get bossadmin password
```shell
cd vault
./bastion.py bastion.integration.boss vault.integration.boss vault-read secret/auth/realm
```
Login to https://api.integration.theboss.io/v0.7/collection/
Uses bossadmin and the password you now have to sync bossadmin to django

## Run unit tests on Endpoint

If you are following these instructions for your personal development environment, skip the
export RUN_HIGH_MEM_TESTS line.  That line runs 2 tests that need >2.5GB of memory
to run and will fail in your environment

```shell
cd vault
./bastion.py bastion.integration.boss endpoint.integration.boss ssh
export RUN_HIGH_MEM_TESTS=true
cd /srv/www/django
sudo python3 manage.py test
```
	output should say Ran 257 tests.


## Proofreader Tests
````shell
cd vault
./ssh.py proofreader-web.integration.boss
cd /srv/www/app/proofreader_apis
sudo python3 manage.py makemigrations --noinput
sudo python3 manage.py makemigrations --noinput common
sudo python3 manage.py migrate
sudo python3 manage.py test
````
    output should say 350 Tests OK

## Integration Tests
After the integration instance is launched the following tests need to be run,
results recorded, and developers notified of any problems.

### Endpoint Integration Tests

#### Test While Logged Onto the Endpoint VM

Again, Skip the RUN_HIGH_MEM_TESTS line below if you are following these instructions for
your personal development environment.  That line runs 2 tests that need >2.5GB
of memory to run and will fail in your environment

```shell
export RUN_HIGH_MEM_TESTS=true
cd /srv/www/django
sudo python3 manage.py test --pattern="int_test_*.py"
```
	output should say 55 Tests OK with 7 skipped tests


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

In your browser, open https://api.integration.theboss.io/token

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
host = api.integration.theboss.io
# Replace with your token.
token = c23b48ceb35cae212b470a23d99d4185bac1c226

[Metadata Service]
protocol = https
host = api.integration.theboss.io
# Replace with your token.
token = c23b48ceb35cae212b470a23d99d4185bac1c226

[Volume Service]
protocol = https
host = api.integration.theboss.io
# Replace with your token.
token = c23b48ceb35cae212b470a23d99d4185bac1c226
```

Additionally, create a copy of `~/.intern/intern.cfg` as `test.cfg` in the intern
repository directory.

##### Setup via the Django Admin Page

In your browser, go to https://api.integration.theboss.io/admin

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
* https://api.integration.theboss.io/ping/
* https://api.integration.theboss.io/v0.7/collection/
* Login into Scalyr and verify that the new instances appear on the overview page.
* Also on Scalyr, check the cloudwatch log for the presence of the instance IDs of the endpoint and proofreader.

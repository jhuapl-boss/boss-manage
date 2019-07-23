# Updating the existing Production stack

This guide helps walk you through the different steps that need to happen 
to update an existing production stack with the latest code.

*Note: This guide assumes that you already have an environment setup and can
successfully launch CloudFormation configurations.*

You will need to have the latest **boss-manage/vault/private/vault.production.boss** directory to complete these steps 

## Rebuild and Update Integration
This is not a mandatory step but it is a good thing to do before the Tag and Merge.
Rebuild the Integration Stack following [IntegrationRebuild.md](IntegrationRebuild.md) using **--ami-version lastSprint**, 
then update the stack with the latest code and test (Follow all the steps in this document for the 
Integration Stack except for Tag and Merge)

## Tag and Merge
Follow the instructions in  [TagAndMerge.md](TagAndMerge.md) to create 
AMIs for sprintXX.  These instructions are still valid however I tend build production based off of the latest AMIs and
only after the process is finished to I copy the latest AMIs and label them sprintXX.  It is not unusual to discover an 
error during the update process that causes a code change and a rebuild of an AMI.

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
## Turn on Maintenance Mode
In boss-manage/cloud_formation run:
```shell
python3 ./maintenance.py on production.boss
```
In can take up to 10 to 15 minutes for DNS to be updated externally.
Use: dig api.theboss.io
to see if DNS has been changed back to ELB.
Once completed you will see a "Down for Maintenance Page" at api.theboss.io

In can take up to 10 to 15 minutes for DNS to be updated externally.  (sometimes its fast)
Use: dig api.theboss.io
to see if DNS has been changed to cloudfront servers.


## Create SprintXX AMIs 
You can either create new AMIs:
```shell
$ cd boss-manage/bin
$  ./packer.py auth vault endpoint cachemanager activities --name sprintXX
```
or copy the latest AMIs from the console to become sprintXX (this way is faster if the AMIs will end up being the same version of code.)

### Backup vault

```shell
$ cd boss-manage.git/bin
$ ./bastion.py vault.production.boss vault-export path/to//file
```

### Updating IAM
Verify IAM Policy, Groups and Roles are the latest.  Master IAM scripts are located boss-manage/config/iam.
Make sure your AWS_CREDENTIALS is set for the dev account
```shell
$ cd boss-manage.git/bin
$ ./iam_utils.py export
```
this will update the boss-manage.git/config/iam files with the latest changes added
to the dev account.  I use git diff on the three files to look over the changes.
* groups.json
* policies.json
* roles.json

If there new information that you believe should not be included in these files you 
can edit iam_utils.py file.  It has keyword filters and whole word filters to 
excluded groups, policies and roles that should not to into the config/iam files.


Make sure your AWS_CREDENTIALS is set for the production account
```shell
$ cd boss-manage.git/bin
$ ./iam_utils.py import
```

### Remove Subscriptions to ProductionMicronsMailingList in SNS 
*Make a note of mailing subscribers so you can add them back in later.*

Delete all subscriptions to Production mailing list except your email address.  Leaving them in place 
will cause multiple emails and texts per minute to everyone on the list.  You need to leave yourself in the list or else when you put everyone back in all the built up
 notifications will come down.
 


### Check Cloud Formation Change sets.
Change sets will automatically be generated when doing an update, but doing it the
way listed below will allow you to dig into the details of any issues.

```shell
$ ./cloudformation.py generate production.boss --scenario production core
```
Now go to CloudFormation in the console
* check CoreProductionBoss
* Under Actions select "Create Change Set For Current Stack"
* Choose "Upload a template to Amazon S3"
* File should be under boss-mange/cloud_formation/templates
* Select the correct .template file. and select Next
* Give it a Change set name and select Next
* On options page just take defaults and select Next
* push *Create change set*

When it completed, look it over to make sure the changes do not require the delete of
anything that holds data, like DynamoDB tables, or RDS tables.  
The deletion of AutoScaleGroups are OK.


### Updating configs

For the *core*, *api* configurations
run the following command. You have to wait for each command to finish before
launching the next configuration as they build upon each other.  

```shell
$ ./cloudformation.py update production.boss --scenario production core
```

*Note: The cloudformation.py script will automatically use the latest created AMIs
that are named with a commit hash.  If you want to use specific AMIs use the **--ami-version***

After completion check that vault still works, look for password:
```shell
./bastion.py vault.production.boss vault-read secret/auth/realm
```

Try to update redis

```shell
$ ./cloudformation.py update production.boss --scenario production redis
```

If the size is not identical you may have to delete the redis config and create it again.
This should be done before updating api.  If you need to delete redis you'll need to make sure 
there are not *write-cuboid* keys in the cache before deleting it.

```shell
$ cd boss-manage.git/bin
./bastion.py endpoint.production.boss ssh
sudo apt-get install redis-tools
redis-cli -h cache.production.boss
select 0
keys WRITE-CUBOID*
```
**Only peform this step if the redis update did not work** If no keys come back it is OK to delete the cache. If keys exist, keep checking, the keys 
should all disappear eventually.  Then delete and create the redis clusters
```shell
$ ./cloudformation.py delete production.boss --scenario production redis
$ ./cloudformation.py create production.boss --scenario production redis
```

Make another template for api and compare it in cloud formation.
```shell
$ ./cloudformation.py generate production.boss --scenario production api 
```

_WARNING if updating API after sprint18 (7/19/18): We have modified the Global Secondary Indexes (GSI) on the Tile DynamoDB Table. If you try and update the API Cloudformation script, it may fail if it tries to remove an old GSI and add a new one.  You'll receive a failure that only once GSI change can occur at a time.  To resolve this edit the ndingest/nddynamo/schemas/boss_tile_index.json file.  If the GSI in your table is different then the named GSI in DynamoDB, edit this file and remove the GSI completely.  Update API and your GSI will be removed. Now put the GSI back in the boss_tile_index.json file and run API update again.  The new GSI will be created._    
 

For *api*, *cachedb*, and *activities* update each stack in sequence

```shell
$ ./cloudformation.py update production.boss --scenario production api
$ ./cloudformation.py update production.boss --scenario production cachedb
$ ./cloudformation.py update production.boss --scenario production activities
```

If cachedb or activities has new lambdas being created for the first time you may get errors like this:
Error updating downsampleVolumeLambda-integration-boss: An error occurred (ResourceNotFoundException) when calling the UpdateFunctionCode operation: Function not found:
In which case you'll need to delete and create both cachedb and activities again:

Error updated cachedb or activities?  do this step:
```shell
$ ./cloudformation.py delete production.boss --scenario production cachedb
$ ./cloudformation.py create production.boss --scenario production cachedb
$ ./cloudformation.py delete production.boss --scenario production activities
$ ./cloudformation.py create production.boss --scenario production activities
```

**Until Delete Step Functions are updated,  turn off the Cloudwatch Rule for Deletes**

* Go to Cloudwatch in the AWS Console
* Under Events -> Rules, select the deleteEventRule.production.boss Rule
* Under the Action menu select Disable


For *cloudwatch* and *dynamolambda* delete and create the cloud formation stacks again.

```shell
$ ./cloudformation.py delete production.boss --scenario production cloudwatch
$ ./cloudformation.py create production.boss --scenario production cloudwatch
$ ./cloudformation.py delete production.boss --scenario production dynamolambda
$ ./cloudformation.py create production.boss --scenario production dynamolambda
```

## Get bossadmin password
```shell
cd vault
./bastion.py vault.production.boss vault-read secret/auth/realm
```
Login to https://api.theboss.io/latest/collection/
Uses bossadmin and the password you now have to sync bossadmin to django

## Turn off Maintenance Mode
In boss-manage/cloud_formation run:
```shell
python3 ./maintenance.py off production.boss
```
In can take up to 10 to 15 minutes for DNS to be updated externally.
Use: dig api.theboss.io
to see if DNS has been changed back to ELB.

### Add Subscriptions to ProductionMicronsMailingList in SNS
Take the list of emails and phone numbers you created earlier and 
add them back into the ProductionMicronsMailingList Topic in SNS.

### Disable Cloudwatch Delete Rules
Go Into Cloudwatch Rules and make sure the **deleteEventRule.production.boss** is disabled

# Testing

### Run unit tests on Endpoint
If you are following these instructions for the integration development environment, skip the
export RUN_HIGH_MEM_TESTS line.  That line runs a few tests that need >2.5GB of memory
to run and will fail in the integration environment

```shell
cd boss-manage.git/bin
./bastion.py endpoint.production.boss ssh
export RUN_HIGH_MEM_TESTS=true
cd /srv/www/django
sudo -E python3 manage.py test
```
	output should say Ran XXX tests.

## Integration Tests
After the integration instance is launched the following tests need to be run,
results recorded, and developers notified of any problems.

### Endpoint Django Integration Tests

Test While Logged onto the Endpoint VM
```shell
export RUN_HIGH_MEM_TESTS=true
cd /srv/www/django
sudo -E python3 manage.py test -- -c inttest.cfg
```
	output should say XXX Tests OK with 7 skipped tests

#### SPDB Integration Tests 
Test while logged onto the Endpoint VM 
```shell
cd /usr/local/lib/python3.5/site-packages/spdb
sudo nose2
sudo nose2 -c inttest.cfg
```

##### 
Test while logged onto the Endpoint VM
```shell
# Manual install for now.  Will likely remove use of pytest in the future.
sudo -H pip3 install pytest
cd /usr/local/lib/python3/site-packages/ndingest
# Use randomized queue names and prepend 'test_' to bucket/index names.
export NDINGEST_TEST=1
pytest -c test_apl.cfg
```

### Cachemanager Integration Tests
Test the ndingest library.
#### Test While Logged onto the Cachemanager VM

```shell
cd /srv/salt/boss-tools/files/boss-tools.git/cachemgr
sudo nose2
sudo nose2 -c inttest.cfg
```
	there is currently issues with some of the tests not getting setup correctly. cache-DB and cache-state-db need to be manutally set to 1.
	or the tests hang.


#### Test Using Intern From a Client

intern integration tests should be run from your local workstation or a VM
**not** running within the production VPC.

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

##### Setup new user for testing  (don't use bossadmin for this)
In your browser, open https://api.theboss.io/vX.Y/token

Your browser should be redirected to the KeyCloak login page.
Create a new account and return to the token page.
This token will be copied-pasted into the intern config file.

then logout and login as bossadmin
Go to boss console 
https://api.production.theboss.io and give your new user
* resource-manager
* user-manager

SSO -> Manager Users, select your user and add the roles

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

#### Run Ingest Tests

* cd ingest-test
* run python3 ./setup_test.py
* Copy the export and and ingest run commands 
* cd ../ingest-client
* paste the copied commands above.
    this should start loading the ingest data
* cd back to the ingest-test directory
* python3 validate_ingest.py


### Automated Tests
To be filled out

### Manual Checks
* https://api.theboss.io/ping/
* https://api.theboss.io/latest/collection/
* Login into Scalyr and verify that the new instances appear on the overview page.
* Also on Scalyr, check the cloudwatch log for the presence of the instance IDs of the endpoint

# Finally 
## Have you created the production sprintXX IAMs yet?
If not copy the latest versions with the sprintXX label.

## Create SprintXX AMIs in developer account 
Its best to create new hash versions of the AMIs like this:
```shell
$ cd boss-manage/bin
$  ./packer.py auth vault endpoint cachemanager
```
And then copy the latest AMIs from the console to become sprintXX 
(this way developers can get the latest AMIs without explicitly specifying sprintXX)


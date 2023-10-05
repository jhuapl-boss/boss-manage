# Updating the existing bossdb stack

This guide helps walk you through the different steps that need to happen 
to update an existing bossdb stack with the latest code.

*Note: This guide assumes that you already have an environment setup and can
successfully launch CloudFormation configurations.*

You will need to have the latest **boss-manage/vault/private/vault.bossdb.boss** directory to complete these steps 

## Rebuild and Update Integration
This is not a mandatory step but it is a good thing to do before the Tag and Merge.
Rebuild the Integration Stack following [IntegrationRebuild.md](IntegrationRebuild.md) using **--ami-version lastSprint**, 
then update the stack with the latest code and test (Follow all the steps in this document for the 
Integration Stack except for Tag and Merge)

## Tag and Merge
Follow the instructions in  [TagAndMerge.md](TagAndMerge.md) to create 
AMIs for sprintXX.  These instructions are still valid however I tend build bossdb based off of the latest AMIs and
only after the process is finished to I copy the latest AMIs and label them sprintXX.  It is not unusual to discover an 
error during the update process that causes a code change and a rebuild of an AMI.

## Turn on Maintenance Mode
In boss-manage/bin/ run:
```shell
python3 ./maintenance.py on bossdb.boss
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
$  ./packer.py bossdb.boss auth vault endpoint cachemanager activities --name sprintXX
```
or copy the latest AMIs from the console to become sprintXX (this way is faster if the AMIs will end up being the same version of code.)

### Backup vault

```shell
$ cd boss-manage.git/bin
$ ./bastion.py vault.bossdb.boss vault-export path/to/file
```

### Updating IAM
Verify IAM Policy, Groups and Roles are the latest.  Master IAM scripts are located boss-manage/config/iam.
Make sure your AWS_CREDENTIALS is set for the dev account
```shell
$ cd boss-manage.git/bin
$ ./iam_utils.py bossdb.boss export groups
$ ./iam_utils.py bossdb.boss export roles
$ ./iam_utils.py bossdb.boss export policies
```
this will update the boss-manage.git/config/iam files with the latest changes added
to the dev account.  I use git diff on the three files to look over the changes.
* groups.json
* policies.json
* roles.json

If there new information that you believe should not be included in these files you 
can edit iam_utils.py file.  It has keyword filters and whole word filters to 
excluded groups, policies and roles that should not to into the config/iam files.


### Remove Subscriptions to ProductionMicronsMailingList in SNS 
*Make a note of mailing subscribers so you can add them back in later.*

Delete all subscriptions to Production mailing list except your email address.  Leaving them in place 
will cause multiple emails and texts per minute to everyone on the list.  You need to leave yourself in the list or else when you put everyone back in all the built up
 notifications will come down.
 


### Check Cloud Formation Change sets.
Change sets will automatically be generated when doing an update, but doing it the
way listed below will allow you to dig into the details of any issues.

```shell
$ ./cloudformation.py generate bossdb.boss core
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
$ ./cloudformation.py update bossdb.boss core
```

*Note: The cloudformation.py script will automatically use the latest created AMIs
that are named with a commit hash.  If you want to use specific AMIs use the **--ami-version***

If the vault policies were updated, this has only happened once since our inception
run the post-init command on core.

```shell script
$ ./cloudformation.py post-init bossdb.boss core
```
Vault policies were updated when adding userthrottle and ingest-complete PRs.

After completion check that vault still works, look for password:
```shell
./bastion.py vault.bossdb.boss vault-read secret/auth/realm
```

Try to update redis

```shell
$ ./cloudformation.py update bossdb.boss redis
```

If the size is not identical you may have to delete the redis config and create it again.
This should be done before updating api.  If you need to delete redis you'll need to make sure 
there are not *write-cuboid* keys in the cache before deleting it.

```shell
$ cd boss-manage.git/bin
./bastion.py endpoint.bossdb.boss ssh
sudo apt-get install redis-tools
redis-cli -h cache.bossdb.boss
select 0
keys WRITE-CUBOID*
```
**Only peform this step if the redis update did not work** If no keys come back it is OK to delete the cache. If keys exist, keep checking, the keys 
should all disappear eventually.  Then delete and create the redis clusters
```shell
$ ./cloudformation.py delete bossdb.boss redis
$ ./cloudformation.py create bossdb.boss redis
```

Make another template for api and compare it in cloud formation.
```shell
$ ./cloudformation.py generate bossdb.boss api 
```

_WARNING if updating API after sprint18 (7/19/18): We have modified the Global Secondary Indexes (GSI) on the Tile DynamoDB Table. If you try and update the API Cloudformation script, it may fail if it tries to remove an old GSI and add a new one.  You'll receive a failure that only once GSI change can occur at a time.  To resolve this edit the ndingest/nddynamo/schemas/boss_tile_index.json file.  If the GSI in your table is different then the named GSI in DynamoDB, edit this file and remove the GSI completely.  Update API and your GSI will be removed. Now put the GSI back in the boss_tile_index.json file and run API update again.  The new GSI will be created._    
 

For *api*, *cachedb*, and *activities* update each stack in sequence

```shell
$ ./cloudformation.py update bossdb.boss api
$ ./cloudformation.py update bossdb.boss cachedb
$ ./cloudformation.py update bossdb.boss activities
```

If cachedb or activities has new lambdas being created for the first time you may get errors like this:
Error updating downsampleVolumeLambda-integration-boss: An error occurred (ResourceNotFoundException) when calling the UpdateFunctionCode operation: Function not found:
In which case you'll need to delete and create both cachedb and activities again:

Error updated cachedb or activities?  do this step:
```shell
$ ./cloudformation.py delete bossdb.boss cachedb
$ ./cloudformation.py create bossdb.boss cachedb
$ ./cloudformation.py delete bossdb.boss activities
$ ./cloudformation.py create bossdb.boss activities
```



For *cloudwatch* it is much faster to update it.  But it is possible to delete and create it. If update doesn't work for some reason.

```shell
$ ./cloudformation.py update bossdb.boss cloudwatch
```

For *idindexing* run update

```shell
$ ./cloudformation.py update bossdb.boss idindexing
```
If it has problems run 

```shell
$ ./cloudformation.py delete bossdb.boss idindexing
$ ./cloudformation.py create bossdb.boss idindexing
```

## Get bossadmin password
```shell
cd vault
./bastion.py vault.bossdb.boss vault-read secret/auth/realm
```
Login to https://api.theboss.io/latest/collection/
Uses bossadmin and the password you now have to sync bossadmin to django

## Turn off Maintenance Mode
In boss-manage/cloud_formation run:
```shell
python3 ./maintenance.py off bossdb.boss
```
In can take up to 10 to 15 minutes for DNS to be updated externally.
Use: dig api.theboss.io
to see if DNS has been changed back to ELB.

### Add Subscriptions to ProductionMicronsMailingList in SNS
Take the list of emails and phone numbers you created earlier and 
add them back into the ProductionMicronsMailingList Topic in SNS.

### Disable Cloudwatch Delete Rules
Go Into Cloudwatch Rules and make sure the **deleteEventRule.bossdb.boss** is disabled

# Testing
See [Testing.md](Testing.md) for running tests on the updated stack.

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
$  ./packer.py <bosslet.config> auth vault endpoint cachemanager
```
And then copy the latest AMIs from the console to become sprintXX 
(this way developers can get the latest AMIs without explicitly specifying sprintXX)


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

## Create SprintXX AMIs 
You can either create new AMIs:
```shell
$ cd boss-manage/bin
$  ./packer.py auth vault consul endpoint proofreader-web cachemanager --name sprintXX
```
or copy the latest AMIs from the console to become sprintXX (this way is faster if the AMIs will end up being the same version of code.)


### Updating IAM
Verify IAM Policy, Groups and Roles are the latest.  Master IAM scripts are located boss-manage/config/iam.
Make sure your AWS_CREDENTIALS is set for the production account

```shell
$ cd boss-manage.git/bin
$ ./iam_utils import
```

### Remove Subscriptions to ProductionMicronsMailingList in SNS 
Delete all subscrioptions to Production mailing list before upgrading.  Leaving them in place
will cause multiple emails and texts per minute to everyone on the list.
*Make a note of the contents so you can add them back in later.*

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

This will show the status of all the consul nodes:
```shell
$ ./bastion.py consul.production.boss ssh-all 'sudo consul operator raft -list-peers; sudo consul members'
```

```shell
$ ./cloudformation.py update production.boss --scenario production api
```

For *cachedb* and *cloudwatch* delete and create the cloud formation stacks again.

```shell
$ ./cloudformation.py delete production.boss --scenario production cachedb
$ ./cloudformation.py create production.boss --scenario production cachedb
$ ./cloudformation.py delete production.boss --scenario production cloudwatch
$ ./cloudformation.py create production.boss --scenario production cloudwatch
```

## Get bossadmin password
```shell
cd vault
./bastion.py vault.integration.boss vault-read secret/auth/realm
```
Login to https://api.theboss.io/v0.7/collection/
Uses bossadmin and the password you now have to sync bossadmin to django

## Add Trigger to multilambda.production.boss
Go to S3 in the AWS console
select tiles.production.boss bucket properties
under Events delete the current Lambda (if there is one)
save

Now Go to Lambda in the AWS console, 
Select multilambda.integration.boss
Select trigger tab
click in the empty box Lambda is pointing to in the diagram.  Now select the S3 in the drop down box.
A new dialog will come up
Bucket:  tiles.production.boss
Event Type:  Object Created (All)
click submit (You may need to scroll down to see the submit button)

### Add Subscriptions to ProductionMicronsMailingList in SNS
Take the list of emails and phone numbers you created earlier and 
add them back into the ProductionMicronsMailingList Topic in SNS.

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

## Integration Tests
After the integration instance is launched the following tests need to be run,
results recorded, and developers notified of any problems.

### Endpoint Integration Tests

#### Test While Logged onto the Endpoint VM
```shell
export RUN_HIGH_MEM_TESTS=true
cd /srv/www/django
sudo python3 manage.py test --pattern="int_test_*.py"
```
	output should say 55 Tests OK with 7 skipped tests

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

### Cachemanager Integration Tests

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
* https://api.theboss.io/v0.7/collection/
* Login into Scalyr and verify that the new instances appear on the overview page.
* Also on Scalyr, check the cloudwatch log for the presence of the instance IDs of the endpoint and proofreader.

# Finally 
## Change AWS Credentials back to dev account
Make sure your:
**boss-manage/config/aws_credentials** file contains the developer account keys
**boss-manage/vault/private/vault_aws_credentials** file contains the developer vault account keys
**boss-manage/config/set_var.sh** should have SSH_KEY=<yourdefault key>

## Create SprintXX AMIs in developer account 
Its best to create new hash versions of the AMIs like this:
```shell
$ cd boss-manage/bin
$  ./packer.py auth vault consul endpoint proofreader-web cachemanager
```
And then copy the latest AMIs from the console to become sprintXX 
(this way developers can get the latest AMIs without explicitly specifying sprintXX)


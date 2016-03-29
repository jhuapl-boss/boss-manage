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

### Running Packer
Make sure that the Packer executable is either in $PATH (you can call it by just
calling packer) or in the `bin/` directory of the boss-manage repository.

Place `microns-bastion20151117.pem` in the `bin` folder.

```shell
$ cd bin
$ ./packer.py vault endpoint proofreader-web
```

*Note: because the packer.py script is running builds in parallel it is redirecting
the output from each Packer subprocess to `packer/logs/<config>.log`. Because of
buffering you may not see the file update with every new line. Tailing the log
does seem to work (`tail -f packer/logs/<config>.log`)*

*Note: the packer.py script will name the AMIs with the hash of the current commit
you are building from. Make sure that all changes have been committed (they don't
have to be pushed yet) so that the correct commit hash is used.*

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
$ cd cloud_formation/
$ source ../config/set_vars.sh
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

*Note: The cloudformation.py script will automatically use the latest created AMIs
that are named with a commit hash. Since you just rebuilt the AMIs they should be
the latest ones.*

## Initialize Endpoint and run unit tests
```shell
cd vault
./ssh.py endpoint.integration.boss
cd /srv/www/django
sudo python3 manage.py makemigrations
sudo python3 manage.py makemigrations bosscore
sudo python3 manage.py migrate
sudo python3 manage.py collectstatic
	: yes
sudo python3 manage.py createsuperuser
	user:  bossadmin
	email: garbage@garbage.com
	pass:  88brain88
sudo service uwsgi-emperor reload
sudo service nginx restart
sudo python3 manage.py test
```
	output should say 36 Tests OK

## Configure Route 53
1. Update Route 53 with the new Loadbalancer dns name.
2. Under the EC2 page select Loadbalancers
3. On description page will be `DNS Name`
3. Copy that
4. Go into Route 53 AWS Service
5. Hosted Zone theboss.io
6. Check checkbox api.theboss.io
7. Paste the new DNS name over top of the old one.
8. `Save Record Set`


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

## Integration Tests
After the integration instance is launched the following tests need to be run,
results recorded, and developers notified of any problems.


### Automated Tests
To be filled out

### Manual Checks
* https://api.theboss.io/ping/
* https://api.theboss.io/v0.2/info/collections/

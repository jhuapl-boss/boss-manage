# BOSS Install Guide

This install guide is designed to guide someone who is setting up a new AWS
account and checking out the source code for the first time.

*Note on style: Any reference to “boss-manage.git/” is a reference to the root
directory of the cloned boss-manage.git repository.*

## Requirements

### Workstation
You will need a Linux machine installed with the following software packages:
* Python 3.5
* Packer ([download](https://www.packer.io/))
* Install Python packages in boss-manage.git requirements.txt.  See *Install Procedures* below to install boss-manage.git then run:
```shell
pip install -r requirements.txt
```
You will need access to an Amazon AWS account with full access to the following
resources:
* CloudFormation
* VPC
* EC2
* RDS
* DynamoDB
* IAM
* Route53
* Cloudwatch
* Certificate Manager


### AWS Account
Under the main account - (logged in with the email address)
* Under Billing and Cost Management -> Preferences
  * Check "Receive PDF Invoice By Email"
  * Check "Receive Billing Alerts" 
  * Save Preferences

####Go into IAM 
* Create Users
* Create group aplAdminGroup and add Policy AdministratorAccess
* Create new Role DeveloperAccess  (only used if you have a Developer account)
    * select "Role for Cross-Account Access" 
    * select "Provide access between AWS accounts you own" 
    * enter in the developer account number and continue
    * enter AdministrativeAccess
* In Developer Account create two new policies.
    * aplDenyAssumeRoleInProduction
```
  {
    "Version": "2012-10-17",
    "Statement": {
        "Effect": "Deny",
        "Action": "sts:AssumeRole",
        "Resource": "arn:aws:iam::451493790433:role/DeveloperAccess"
    }
  }
```
    * aplAllowAssumeRoleInProduction
```
  {
    "Version": "2012-10-17",
    "Statement": {
        "Effect": "Allow",
        "Action": "sts:AssumeRole",
        "Resource": "arn:aws:iam::451493790433:role/DeveloperAccess"
    }
  }
```
* Now Create two new Groups and add policies above to them.
    * aplDenyProductionAccountAccess
    * aplProductionAccountAccess
    
* under "Account Settings" setup appropriate password settings

*Note: you will also need access to the API keys for the AWS account.*

### Github Repositories
You will need access to the following code repositories on Github:
* [boss-manage.git](https://github.com/jhuapl-boss/boss-manage)
* [boss-tools.git](https://github.com/jhuapl-boss/boss-tools)
* [boss.git](https://github.com/jhuapl-boss/boss)
* [spdb.git](https://github.com/jhuapl-boss/spdb)
* [ingest.git](https://github.com/jhuapl-boss/ingest-client)
* [ndingest.git](https://github.com/jhuapl-boss/ndingest)

## Install Procedures

### Clone boss-manage repository
Before a new copy of the BOSS architecture can be created / instantiated, the
boss-manage.git repository, and submodules, need to be cloned.

```shell
$ git clone --recursive https://github.com/jhuapl-boss/boss-manage.git
```

### Create AWS credentials file
For all of the scripts to access AWS the access key and secret key for your AWS
account as stored in a configuration file that all of the scripts use.

1. Copy `boss-manage.git/config/aws-credentials.example` to
`boss-manage.git/config/aws-credentials`
2. Open `aws-credentials` in a text editor
3. Enter the access key and secret key for your AWS account
4. Save `aws-credentials` and close the text editor

### Create AWS bastion file
If you have a corporate firewall that limits outbound SSH access all of the
scripts used can tunnel their communication through a bastion host. A bastion
host is a single machine which your corporate IT department has granted you
outbound SSH access to. All SSH traffic will be tunneled through that machine.
It is assumed that this bastion host is an EC2 instance running within AWS.

1. Copy the SSH private key for the bastion host into `boss-manage.git/bin/`
2. Open  `boss-manage.git/config/aws-bastion` in a text editor
3. Edit the IP address of the machine
4. Edit the name of the private key
  * The directory reference "./" should stay the same
5. Save `aws-bastion` and close the text editor

*Note: these instructions are written expecting a bastion host. If you are not
using one, then you can remove those extra arguments from the few steps where
they are configured.*

### Run One time setup script to create
```shell
$ bin/one_time_aws_account_setup.py --aws-credentials /path/to/credentials
```
this is create 
* Topics
* Billing Alarms
* Policies
* Roles
* Groups

### Setup Hosted Zone for domain name: theboss.io
In Route53 create a new hosted zone for the theboss.io
Change the Name Servers within your domain registrar to use the ones listed
in the newly created hosted zone.


### Create AMIs
Several AWS Images (AMIs) need to be created. These images are preconfigured for
specific roles within the architecture. These procedures expect the AWS
credentials and AWS bastion files described in the previous two sections.

Make sure that the Packer executable is either in $PATH (you can call it by just
calling packer) or in the `bin/` directory of the boss-manage repository.

```shell
$ bin/packer.py auth vault endpoint proofreader-web consul cachemanager
```

*Note: because the packer.py script is running builds in parallel it is redirecting
the output from each Packer subprocess to `packer/logs/<config>.log`. Because of
buffering you may not see the file update with every new line. Tailing the log
does seem to work (`tail -f packer/logs/<config>.log`)*
Check for Success or failure with the command below:
```shell
$ grep "artifact" ../packer/logs/*.logs
```

Success looks like this:
==> Builds finished. The artifacts of successful builds are:
Failure like this
==> Builds finished but no artifacts were created.

It can beneficial to check the logs before all the AMIs are completed, 
when issues do occur, they frequently fail early.  Discovering this 
allows you to relauch packer.py in another terminal for the failed AMIs,
saving time overall.

#### Running Lambda packer
From the packer 
```shell
$ cd boss-manage.git/packer
$ packer build -var-file=../config/aws-credentials -var-file=variables/lambda -var-file=../config/aws-bastion -var 'force_deregister=true' lambda.packer
```

Manually create security group for the lambda_build_server
Group Name: Bastion-to-Default-VPC
VPC: default-vpc
Inbound ports: 22
From: 52.3.13.189/32

Manually create an instance of the new Lambda-AMI, 
Role: lambda_build_server
Security Group: Bastion-to-Default-VPC
Instance Type: t2.micro
Auto-assign Public IP: enabled
VPC: default-vpc
check: Protect against accidental termination

### Configure IAM Vault account
For Vault to be able to generate AWS credentials it needs to be configured with
an AWS account that has access to specific resources.

1. Copy `boss-manage.git/config/aws-credentials.example` to
`boss-manage.git/vault/private/vault_aws_credentials`
  * You may have to create the directory "private"
2. Open `vault_aws_credentials` in a text editor
3. Open a web browser
4. Login to the AWS console and open up the IAM console
5. Select **Users** from the left side menu
6. Click **Create New Users**
7. Give the Vault account a name
8. Make sure "Generate an access key for each user" is checked
9. Click **Create**
10. Copy the access key and secret key from the browser into the text editor
11. Verify the account and domain names are set correctly in credentials file
12. Save `vault_aws_credentials` and close the text editor
13. Click **Close** in the web browser
14. Scroll down the user list and click on the new Vault account
15. Click the **Permissions** tab
16. Click **Attached Policy**
17. Select **aplVaultPolicy** and click **Attach Policy**

### Configure Scalyr account
1. Create `boss-manage.git/config/scalyr_keys.sh` with the following
content
```bash
#!/bin/bash

export scalyr_readconfig_token='<the read config key>'
export scalyr_writeconfig_token='<the write config key>'
```
2. Open the page at https://www.scalyr.com/keys
3. Copy the scalyr_readconfig_token and scalyr_writeconfig_token from the Scalyr
page into the `scalyr_keys.sh` file
4. Save `scalyr_keys.sh`

*Note: these instructions are written expecting Scalyr integration. This is not
required. If you are not using Scalyr you can remove the extra commands from the
few steps below.*

### Create EC2 Key Pair
1. Open a web browser
2. Login to the AWS console and open up the EC2 console
3. Select **Key Pairs** from the left side menu
4. Click **Create Key Pair**
5. Name the key pair
6. Click **Create**
7. Save the resulting private key / PEM file under `~/.ssh`
8. Run the following command to change file permissions
```shell
$ chmod 400 ~/.ssh/<keypair>.pem
```

*Note: Make sure they the name of the key is the same as the name as entered in
AWS. Characters like '.' may be removed from the file name. It is important that
the name matches exactly, plus '.pem'*


### Launch Configurations
To fully create a new instance of the BOSS architecture several configuration
files are use. The configuration files generate and then launch AWS
CloudFormation Stacks. If there are problems launching the stacks or if you want
to delete the resources launched by these stacks, login to the CloudFormation
AWS console and review or delete the stacks.

#### Environment Setup
The scripts make use of multiple environment variables to manage optional
configuration elements. There are shell scripts that contain these environment
variables that can be sourced before launching different scripts.

1. Open `boss-manage.git/vault/set_keys.sh` in a text editor
2. Update SSH_KEY to contain the location of the EC2 Keypair created
3. Update the BASTION_KEY to contain the location of the private key of the SSH bastion host
4. Update the BASTION_IP to contain the IP of the SSH bastion host
5. Save `set_keys.sh` and close the text editor
```shell
$ cd boss-manage.git/bin/
$ source ../config/set_vars.sh
$ source ../config/scalyr_keys.sh
```

### Setting up Certificates in Amazon Certificates Manage.
You will need to create certificates for auth and api in the domain
(theboss.io) These only needs to be setup once.
You will need to create a EC2 instance to route mail.  Create a micro
Ubuntu instance.
Installed postfix and setup theboss.io as a "virtual alias domain"
sudo apt-get install postfix

change /etc/postfix/main.cf:
    virtual_alias_domains = theboss.io
    virtual_alias_maps = hash:/etc/postfix/virtual

created new file /etc/postfix/virtual:
    admin@theboss.io	your-email-address
your-email-address is a valild address that will recieve the request to
validate that the certicate should be created.

In Route53 create an MX record for theboss.io and add your public instance DNS name to it.

Now You will need to setup the request
cd boss-manage/bin/
python3.5 create_certificate.py api.theboss.io
python3.5 create_certificate.py auth.theboss.io

After you receive the certificate approval emails, turn off the mail instance.


### Launching configs

For the *core*, *redis*, *api*, *cachedb*, *activities*, *cloudwatch* *dynamolambda* configurations
run the following command. You have to wait for each command to finish before
launching the next configuration as they build upon each other.  **Only use the
*--scenario production* flag** if you are rebuilding integration.  It is not used
if you are following these instructions to build a developer environment.
```shell
$ ./cloudformation.py create integration.boss --scenario production <config>
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
./bastion.py vault.integration.boss vault-read secret/auth/realm
```
Login to https://api.theboss.io/
Uses bossadmin and the password you now have to sync bossadmin to django

## Run unit tests on Endpoint 

If you are following these instructions for your personal development environment, skip the 
export RUN_HIGH_MEM_TESTS line.  That line runs 2 tests that need >2.5GB of memory
to run and will fail in your environment

```shell
cd vault
./bastion.py endpoint.integration.boss ssh
export RUN_HIGH_MEM_TESTS=true
cd /srv/www/django
sudo -E python3 manage.py test
```
	output should say 230 Tests OK with 11 skipped tests.


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
sudo -E python3 manage.py test -- -c inttest.cfg
```
	output should say 84 Tests OK with 7 skipped tests


### Cachemanager Integration Tests

#### Test While Logged Onto the Cachemanager VM

```shell
cd /srv/salt/boss-tools/files/boss-tools.git/cachemgr
sudo nose2
sudo nose2 -c inttest.cfg
```
	there is currently issues with some of the tests not getting setup correctly. cache-DB and cache-state-db need to be manutally set to 1.
	or the tests hang.


#### Test Using ndio From a Client

ndio integration tests should be run from your local workstation or a VM
**not** running within the integration VPC.

First ensure ndio is current:

```shell
# Clone the repository if you do not already have it.
git clone https://github.com/jhuapl-boss/ndio.git

# Otherwise update with `pull`.
# git pull

# Make the repository the current working directory.
cd ndio

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

This token will be copied-pasted into the ndio config file.

```shell
mkdir ~/.ndio
EDITOR ~/.ndio/ndio.cfg
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
token = cxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Additionally, create a copy of `~/.ndio/ndio.cfg` as `test.cfg` in the ndio
repository directory.

##### Setup via the Django Admin Page

In your browser, go to https://api.theboss.io/admin

Login using the bossadmin account created previously (this was created during
the endpoint initialization and unit test step).

Click on `Users` and determine the user name based on the email address you
used during account creation (this step should soon be unnecessary, but at the
time of writing, GUIDs are used for the user name).

Now go back to the root admin page.

Click on `Boss roles`.

Click on `ADD BOSS ROLE`.

Find the user you created and add the `ADMIN` role to that user and save.


##### Run ndio Integration Tests

Finally, open a shell and run the integration tests:

```shell
# Go to the location of your cloned ndio repository.
cd ndio.git
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
* https://api.theboss.io/v0.4/resource/collections
* https://api.theboss.io/v0.5/resource/collections
* Login into Scalyr and verify that the new instances appear on the overview page.
* Also on Scalyr, check the cloudwatch log for the presence of the instance IDs of the endpoint and proofreader.


### Setting Up Web Page
Create a S3 bucket named: **www.theboss.io**
Under propertes of the bucket in the **Static Website Hosting** section
click **Enable Website Hosting**
Index Document: index.html
Redirect rules should have
```
<RoutingRules>
    <RoutingRule>
        <Redirect>
            <Protocol>http</Protocol>
            <HostName>docs.theboss.io</HostName>
            <ReplaceKeyPrefixWith/>
            <HttpRedirectCode>301</HttpRedirectCode>
        </Redirect>
    </RoutingRule>
</RoutingRules>
```

Under Route53 two CNAME records in the hosted zone theboss.io 
1. docs.theboss.io 
    * the web server hosting theboss documentation.
2. www.theboss.io
    * the S3 bucket name which is currently:
    * www.theboss.io.s3-website-us-east-1.amazonaws.com

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

### AWS Account
Under the main account - (logged in with the email address)
* Under Billing and Cost Management -> Preferences
** Check "Receive PDF Invoice By Email"
** Check "Receive Billing Alerts" and configure Appropriate alarms in CloudWatch
** Save Preferences

Go into IAM 
* Create Users
* Create group aplAdminGroup and add Policy AdministratorAccess
* under "Account Settings" setup appropriate password settings

Run One time setup script to create 
* Topics
* Policies
* Roles
* Groups




You will need access to an Amazon AWS account with full access to the following
resources:
* CloudFormation
* VPC
* EC2
* RDS
* DynamoDB
* IAM
* Route53

*Note: you will also need access to the API keys for the AWS account.*

### Github Repositories
You will need access to the following code repositories on Github:
* [boss-manage.git](https://github.com/aplmicrons/boss-manage)
* [boss-tools.git](https://github.com/aplmicrons/boss-tools)
* [boss.git](https://github.com/aplmicrons/boss)
* [proofread.git](https://github.com/aplmicrons/proofread)
* [spdb.git](https://github.com/aplmicrons/spdb)

## Install Procedures

### Clone boss-manage repository
Before a new copy of the BOSS architecture can be created / instantiated, the
boss-manage.git repository, and submodules, need to be cloned.

```shell
$ git clone --recursive https://github.com/aplmicrons/boss-manage.git
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

### Create AMIs
Several AWS Images (AMIs) need to be created. These images are preconfigured for
specific roles within the architecture. These procedures expect the AWS
credentials and AWS bastion files described in the previous two sections.

Make sure that the Packer executable is either in $PATH (you can call it by just
calling packer) or in the `bin/` directory of the boss-manage repository.

```shell
$ bin/packer.py vault auth endpoint proofreader-web
```

*Note: because the packer.py script is running builds in parallel it is redirecting
the output from each Packer subprocess to `packer/logs/<config>.log`. Because of
buffering you may not see the file update with every new line. Tailing the log
does seem to work (`tail -f packer/logs/<config>.log`)*

### Configure IAM Vault account
For Vault to be able to generate AWS credentials it needs to be configured with
an AWS account that has access to specific resources.

1. Copy `boss-manage.git/packer/variables/aws-credentials.example` to
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
11. Save `vault_aws_credentials` and close the text editor
12. Click **Close** in the web browser
13. Scroll down the user list and click on the new Vault account
14. Click the **Permissions** tab
15. Expand the **Inline Policies** section
16. Click the **click here** link to create a policy
17. Select **Custom Policy** and click the **Select** button
18. Name the policy “IAM access”
19. Copy the contents of `boss-manage.git/vault/policies/vault.iam.example` into
the **Policy Document** area
20. Click **Validate Policy**
21. Click **Apply Policy**

### Configure Scalyr account
1. Create `boss-manage.git/cloudformation/scalyr_keys.sh` with the following
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

### Configure Route53
Configure the domain theboss.io to be used by route53.


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
$ cd cloudformation/
$ source ../vault/set_vars.sh
$ source ../scalyr_keys.sh
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
    administrator@theboss.io	your-email-address
your-email-address is a valild address that will recieve the request to
validate that the certicate should be created.

In Route53 create an MX record for theboss.io and add your public instance DNS name to it.

Now You will need to setup the request
cd boss-manage/bin/
python3.5 create_certificate.py api.theboss.io
python3.5 create_certificate.py auth.theboss.io

After you receive the certificate approval emails, turn off the mail instance.


#### Launching
For the *core*, *api*, *proofreader* and *cloudwatch* configurations
run the following command. You have to wait for each command to finish before
launching the next configuration as they build upon each other.
```shell
$ ./cloudformation.py create production.boss --scenario production <config>
```

*Note: If when launching the core configuration you receive a message about
manually initializing / configuring Vault then run the following commands. If
they error out then please contact the repository maintainers.*
```shell
$ cd ../vault/
$ ./bastion.py bastion.production.boss vault.production.boss vault-init
$ cd ../cloudformation/
```

## Initialize Endpoint and run unit tests
```shell
cd vault
./bastion.py bastion.integration.boss endpoint.integration.boss ssh
cd /srv/www/django
sudo python3 manage.py createsuperuser
	user:  bossadmin
	email: bossadmin@jhuapl.com
	pass:  xxxxxxxx
sudo python3 manage.py test
```
	output should say 203 Tests OK with 14 skipped tests.

	There are 2 tests that need >2.5GB of memory to run. To run them, set an enviroment variable "RUN_HIGH_MEM_TESTS"

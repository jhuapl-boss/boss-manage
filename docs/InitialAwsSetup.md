# Initial AWS Account Setup

This guide is designed to guide someone through the steps needed to setup a new AWS account to be ready to run a Boss instance.

*Note: This guide assumes that you have already installed the needed requirements and have cloned the boss-manage.git repository*

*Note on style: Any reference to “boss-manage.git/” is a reference to the root
directory of the cloned boss-manage.git repository.*

## Clean up AWS Account

### Set name for default VPC
* in AWS Console under VPCs - Your VPCs - fill in the name "default-vpc" to the default vpc.

## Create a primary bastion server
While not necessary for operation it.  It is often nice to have primary 
bastion server that you can direct to only allow access from your companies 
IP address range.  Then you can put a hole in your corporate firewall for port 22 
to the bastion server. This is helpful when creating multiple Boss stacks, example
production, develop and testing stacks.  

### Create a bastion key pair
* In the AWS Console under EC2 - Key Pairs: "Create Key Pair" for the bastion server
* Save the key pair under `~/.ssh/` with a `.pem` extension
* Change the merssions to 0400 (`chmod 400 <key_pair>.pem`)

### Create an EC2 instance
To create a bastion server, create a new t2.micro or t3.micro (t3.micro is latest generation, however t2.micro is consider free tier) with the Linux flavor of your choice, 
set it up in the default VPC or create a new VPC just for the bastion server.  The server will need a Public IP Address.  Use the new key pair when prompted.

### Create an elastic IP
* In the AWS Console under EC2 - Elastic IP: "Allocate new address".
* Assign the new address to your bastion server.

## Create Bosslet config

### Create IAM user
* Manually create IAM user with API keys and full permissions in AWS Console

### Create user key pair
* In the AWS Console under EC2 - Key Pairs: "Create Key Pair" for the Bosslet user
* Save the key pair under `~/.ssh/` with a `.pem` extension
* Change the merssions to 0400 (`chmod 400 <key_pair>.pem`)

### Create Bosslet config
* Create a copy of `config/boss_config.py.example` as `config/<bosslet_name>.py`
  - Note: Any underscores (`_`) will be replaced by a period (`.`) by the boss-manage CLI applications
* Edit the new bosslet config file with information about the bosslet
  - The example file is well commented, including comments at the bottom detailing which variables need to be set for initial account setup
  - See [InitialBossSetup](InitialBossSetup.md) for more information about setting up a new Boss instance
* Verify the configuration file is correct by running `bin/boss-config.py <bosslet.name>`

### Import IAM resources
* Run `bin/iam_utils.py <bosslet.name> import roles groups policies` to import the initial IAM configuration

### Update IAM user permissions
* Remove full permissions from the IAM user and add them to the `XXXXXX` IAM group
  - Any other Developer or Maintainer should be added to the `XXXXXX` IAM group so they have the needed permissions to manipulate and work with Boss resources

## Create lambda build server
### Build AMI using Packer
```sh
$ bin/packer.py <bosslet_config> lambda --ami-version "" -f
```

## Create Elastic IP needed for lambda build server
* Under AWS Console EC2 - Elastic IP -  "Allocate New Address"
* Choose "Amazon Pool" - Allocate
* Fill in the name of the Elastic IP as "lambda_build_server"

### Create security group
Manually create security group for the lambda_build_server
* Group Name: Bastion-to-Default-VPC
* VPC: default-vpc
* Inbound ports: 22
* From: <bastion server ip>/32

### Manually create an instance of the new Lambda-AMI, 
* Under My AMIs choose lambda.boss
* Role: lambda_build_server
* Security Group: Bastion-to-Default-VPC
* Instance Type: t2.micro
* Auto-assign Public IP: enabled
* VPC: default-vpc
* check: Protect against accidental termination

After Lambda Build Server come up assign it the name "Lambda Build Server"
Attach the elastic IP address: lambda_build_server_ip

### Update Bosslet config
* Edit the bosslet config and update the lambda build server variables with the new information

## Create alerts

### Billing Alerts
* Run `bin/boss-account.py <bosslet.name> billing --create --add <email.address@company.tld> --ls` to create billing alarms
  - This requires the optional `BILLING_THRESHOLDS` Bosslet configuration value to be defined
  - This is optional and only needed if you want to receive notification once the AWS monthly bill exceeds the given threashold(s)

### Error Alerts
* Run `bin/boss-account.py <bosslet.name> alerts --create --add <email.address@company.tld> --ls` to create the alerting mailing list
  - This is used by different Boss processes to alert the developer(s) or maintainer(s) that a problem was encountered and attention is needed to resolve it

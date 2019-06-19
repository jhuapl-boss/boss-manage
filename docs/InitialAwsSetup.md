# Initial AWS Account Setup

## Requirements

### Workstation
You will need a Linux machine installed with the following software packages:
* Python 3.5
* pip install virtualenv virtualenvwrapper
* Packer ([download](https://www.packer.io/)) Version 1.1.1 (add it to your path)
* NodeJS ([download](https://nodejs.org/en/download/)) Version 6.10.X (add it to your path)

## Starting IAM User
* Manually create IAM user with API keys and full permissions in AWS Console

## Setup name for default VPC
* in AWS Console under VPCs - Your VPCs - fill in the name "default-vpc" to the default vpc.

## Setup a primary bastion server
While not necessary for operation it.  It is often nice to have primary 
bastion server that you can direct to only allow access from your companies 
IP address range.  Then you can put a hole in your corporate firewall for port 22 
to the bastion server. This is helpful when creating multiple bossdb stacks, example
production, develop and testing stacks.  

### Create a bastion key pair.
* In the AWS Console under EC2 - Key Pairs: "Create Key Pair" for the bastion server

### Create a new key pair for the first bosslet
* In the AWS Console under EC2 - Key Pairs: "Create Key Pair" for the <your_bosslet_name>

Move both key pairs to the ~/.ssh directory. Change the name to end in .pem instead of .pem.txt if that is what it currently is.  
Change the properties of both pem files to 400
```sh
chmod 400 <name>.pem
``` 

### Create new instance for Bastion
To create a bastion server, create a new t2.micro or t3.micro (t3.micro is latest generation, however t2.micro is consider free tier) with the Linux flavor of your choice, 
set it up in the default VPC or create a new VPC just for the bastion server.  The server will need a Public IP Address.  Use the new key pair when prompted.

### Give the bastion server an elastic IP
In the AWS Console under EC2 - Elastic IP: "Allocate new address".  Assign the new address to your bastion server.  You
have port 22 opened in your companies firewall to that bastion server.


## Create Elastic IP needed for lambda build server
* Under AWS Console EC2 - Elastic IP -  "Allocate New Address"
* Choose "Amazon Pool" - Allocate
* Fill in the name of the Elastic IP as "lambda_build_server"


## Setting up the public domain

* Purchase a domain name, externally or through Route53
* Add it to Route53, so that Route53 manages the DNS records for the domain name
* Request a wildcard certificate `*.domain.tld`, either externally or using Amazon Certificate Manager (ACM)
  - Using Domain validation is the easier, and suggested, approach if using ACM. There should be a link after requesting the certificate in ACM.
  - If you don't want to get a wildcard certificate you need to request `api.domain.tld` and `auth.domain.tld` certificates. If you plan to run multiple Bosslets under the given domain then the certificates will be something _like_ `api.sub.domain.tld` and `auth.sub.domain.tld`, though you can modify the Bosslet configuration `EXTERNAL_FORMAT` value to be whatever you want.
* Wait until the certificate request has been verificated and the SSL certificate is issued
  - If you used ACM then you don't need to do anything else
  - If you requested the certificate externally you need to import the certificate and private key into ACM so that AWS resources can use the SSL certificate

Any Bosslet using the domain can now lookup the certificate(s) needed and attach them to the load balancers to provide HTTPS traffic
  
## AWS IAM Permisions
* Create a Bosslet configuration, using `config/boss_config.py.example` as the template
  - To verify that the configuration file is correct and includes the needed values you can run `bin/boss-config.py <bosslet.name>`
* Run `bin/iam_utils.py <bosslet.name> import roles groups policies` to import the initial IAM configuration
* Remove full permissions from the IAM user and add them to the `XXXXXX` IAM group
  - Any other Developer or Maintainer should be added to the `XXXXXX` IAM group so they have the needed permissions to manipulate and work with Boss resources

## Create the lambda build server using packer

### Clone the boss-manage.git repository recursively.
```sh
$ git clone --recursive https://github.com/jhuapl-boss/boss-manage.git 
```

Create a virtual environment for working with bossdb and pip install the requirements in it.
```sh
$ pip install -r boss-manage.git/requirements.txt
```

### build Lambda Build Server AMI using Packer
```sh
$ bin/packer.py <bosslet_config> lambda --ami-version "" -f
```

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

## Billing Alerts
* Run `bin/boss-account.py <bosslet.name> billing --create --add <email.address@company.tld> --ls` to create billing alarms
  - This requires the optional `BILLING_THREASHOLDS` Bosslet configuration value to be defined
  - This is optional and only needed if you want to receive notification once the AWS monthly bill exceeds the given threashold(s)

## Error Alerts
* Run `bin/boss-account.py <bosslet.name> alerts --create --add <email.address@company.tld> --ls` to create the alerting mailing list
  - This is used by different Boss processes to alert the developer(s) or maintainer(s) that a problem was encountered and attention is needed to resolve it

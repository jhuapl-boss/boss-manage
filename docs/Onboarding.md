# BOSS Onboarding Process
This supplement provides guidance to new development team members and helps them navigate through the steps required to setup their local development environment and deploy a development stack.

A new team member will need to provide them access to the following:

1. An AWS IAM account on [thebossdev](https://thebossdev.signin.aws.amazon.com/console) with credentials that enable aws cli use
2. Access to the [APL Microns](https://github.com/aplmicrons) repository. The new user will need a bosslet config created and the ability to download the bosslet-configs project.
3. Access to the [JHUAPL Boss](https://github.com/jhuapl-boss) repository to pull and make code commits.

# Development Envrionment
The [Installation Guide](./InstallGuide.md) is geared to installing BossDB in new AWS subscription. It covers many of the topics you won't need to get into right now. This **onboarding guide** will highlight what you need to do to get up and running quickly.  However any Python virtual environment may be used, so used whatever you are comfortable using.

## Choose your Python Distribution
This guide assumes you have installed anaconda for python 3. You can download the installer for your platform from [Anaconda](https://www.anaconda.com/products/individual). 

## Create a python 3.7 virtual environment
You should setup a virtual environment with python 3.7. This can be easily accomplished by using the conda command to create a virtual environment e.g. 
`conda create -n bossdb37 python=3.7`

After creating the virtual environment, you can activate it with the following command:
`conda activate bossdb37`

## Download the code
For now, you can just clone the boss-manage repository. The other code repositories will be available as git submodules. 

### github account
You will need a github account in order to be added to the repositories. Make sure you have created ssh keys on your development platform and have added the public key to your github profile.

### pull the code
See the [Clone Repositories](./InstallGuide.md#Clone_Repositories) section of the install guide for links to the code. With your virtual python environment activated, you should install the boss-manage requirements.

## AWS Account
You will be provided with a credentials file for your AWS login on **thebossdev**. You will this to login to AWS console and to use the boss-manage scripts. 

### credentials CSV
The csv file contains both your console login credentials and your command line tool credentials. The 5-column header is shown below:

```shell
User name,Password,Access key ID,Secret access key,Console login link
```

You should attempt to logn by pasting the **Console login link** into your browser and entering in the **User Name** and **Password** found in the credentials file. 

### Bastion Host key
You will also need a pem file for the bastion host on the development account. Place the pem file in your ```~/.ssh/``` folder. You will need this to complete your bosslet config setup.

### bosslet configs
You will need to place the bosslet-configs repository inside the boss-manage codebase under ```./boss-manage/config/custom``` folder. 

```bash
cd ./boss-manage/config
git clone https://github.com/aplmicrons/bosslet-configs.git custom
```
There should be a python file in this folder named with your 5-2-1. This is the name of your **bosslet config**. If it doesn't exist, use the test_boss.py as a template. Modify the ```set-developer('test')``` line and replace test with your 5-2-1. Add the following line:

```shell
SSH_KEY = 'name of bastion host pem file'
```

### boto3 SDK
The boss-manage scripts use the boto3 api to interact with AWS. You need to either create or add to the ~/.aws/credentials file. You should use a section header that matches PROFILE setting in ```./boss-manage/config/custom/apl_developer.py```. The example below should work unless the file content has changed.

```shell
[thebossdev]
aws_access_key_id = [Access key ID]
aws_secret_access_key = [Secret access key]
```
### SSH From Home
If you are working outside of the APL VPN, you will need to add your IP address to the AWS security group named **SSH From Home**. 

# Deploy your stack
Assuming you have completed all of the previous steps, you can now create your own stack on thebossdev. 

## Run the cloudformation script
From the root of the boss-manage code, you can create your stack using the cloudformation python script. This process will take quite some time and you will need to  respond to prompts.

Assuming your bosslet config file is named with your 5-2-1, you can use the following command to create your stack. 

```shell
cd ./boss-manage
python ./bin/cloudformation.py create <your 5-2-1> core redis api cachedb activities cloudwatch dynamolambda
```

## Check AWS
You can use the AWS console to watch your stack creation progress. 

### cloudformation progress
You can try this [cloudformation](https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks?filteringText=&filteringStatus=active&viewNested=true&hideStacks=false&stackId=) link to go directly to the cloudformation page. Otherwise, choose services in the console and click on cloudformation. You may need to use the filter to show only those stacks that have your 5-2-1 in the name. 

### virtual machine instances
If you view EC2 instances and filter by your 5-2-1, you will see a growing list of machines that are being created to support your stack. For example, my 5-2-1 is wilsopw1 so I will see the following machine names:

*  vault.wilsopw1.boss
*  endpoint.wilsopw1.boss
*  cachemanager.wilsopw1.boss
*  bastion.wilsopw1.boss
*  auth.wilsopw1.boss
*  activities.wilsopw1.boss

For now, just know that your boss **api** stack is running on the **endpoint** instance. Also note that each instance is booted from an Amazon Machine Instance (AMI). Building the AMIs only needs to be done when code / configuration changes.  

## Login to BOSS
After your stack has been deployed, you can login to the UI.

### pull secrets
You will need to pull secrets from vault so you can login to your boss UI. 

```shell
cd ./boss-manage
bin/bastion.py vault.wilsopw1.boss vault-export secrets.txt
```
### lookup bossadmin password
Open the secrets.txt file and find the password for **bossadmin** account. An example snippet is shown below.

```json
   "secret/auth/realm": {
      "client_id": "endpoint",
      "password": "TITMaquAGo0aSBxd",
      "username": "bossadmin"
   },
```

### login
Use your browser to navigate to your instance of the boss UI. The url will look something like this: https://api-wilsopw1.thebossdev.io/. You will need to replace wilsopw1 with your 5-2-1. 

You should be redirected to the keycloak login page. Enter **bossadmin** as the username and use the password retrieved from vault.





# Copyright 2019 The Johns Hopkins University Applied Physics Laboratory
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

""" Lambda to launch ec2-instances """
import boto3
import os

REGION = os.environ['AWS_REGION'] # region to launch instanc leveraging lambda env var.
AMI = 'ami-456b493a' # Ubuntu 16.04 AWS provided base image.
INSTANCE_TYPE = 't2.micro' # instance type to launch.

EC2 = boto3.client('ec2', region_name=REGION)

def lambda_to_ec2(event, context):
    """ Lambda handler taking [message] and creating a httpd instance with an echo. """

    # bash script to run:
    #  - boss-manage commands to build stack
    #  - run tests using the instance's shell
    #  - send all results to an S3 bucket
    #  - send out completion SNS
    #  - set to shutdown the instance automatically in 60 minutes.
    init_script = """#!/bin/bash
echo ' '
echo 'echo "----------------------Init_Script----------------------'
echo ' '

set -e 

#Install python3.5 and guide pip to it
yes | apt-get update
yes | ufw allow 22
yes | apt-get install python3.5
yes | apt-get install zip unzip
yes | apt-get install jq
yes | apt-get install python3-pip

cd /home/ubuntu/

# Create dummy .aws configs
mkdir .aws
cd .aws
touch credentials
touch config
cd ..

#Install git
yes | apt-get install git

# Compile Packer binary from source
wget https://releases.hashicorp.com/packer/0.12.0/packer_0.12.0_linux_amd64.zip
unzip packer_0.12.0_linux_amd64.zip -d packer
wait
echo sudo mv packer /usr/bin/
sudo mv packer /usr/bin/
echo export PATH="/usr/bin/packer:$PATH"
export PATH="/usr/bin/packer:$PATH"

#Clone github repo and install requirements
git clone https://github.com/jhuapl-boss/boss-manage.git
wait

#Checkout the right branch
cd boss-manage/
git checkout auto-build-test
# git checkout 8a55840

#Install all requirements
git submodule init
git submodule update
python3.5 -m pip install -r requirements.txt

cd salt_stack/salt/boss-tools/files/boss-tools.git
git checkout vault_update
cd ../../../../../

# Set-up log records on Cloudwatch:
export EC2_REGION=`curl --silent http://169.254.169.254/latest/dynamic/instance-identity/document | jq -r .region`
curl https://s3.amazonaws.com/aws-cloudwatch/downloads/latest/awslogs-agent-setup.py -O
(echo
 echo
 echo
 echo /var/log/cloud_init_output.log
 echo 1
 echo 1
 echo N) | python3 ./awslogs-agent-setup.py --region $EC2_REGION

#Make vault private directory
mkdir vault/private

#Make empty aws-creds file so that cloudformation script works properly.
cd config/
touch aws-credentials
source set_vars-auto_build_test.sh
cd ../bin/

#Create  keypair to attach to ec2 instances made by cloudformation.
python3.5 ./manage_keypair.py delete auto-build-keypair
python3.5 ./manage_keypair.py create auto-build-keypair
export SSH_KEY="~/.ssh/auto-build-keypair.pem"
chmod 400 ~/.ssh/auto-build-keypair.pem
# ssh-add ~/.ssh/auto-build-keypair.pem
wait

#Build AMIs
echo " "
echo "----------------------Building AMIs----------------------"
echo " " 
python3.5 ./packer.py auth vault consul endpoint cachemanager activities --name autotest --no-bastion
wait

echo " "
echo "----------------------Create Stack----------------------"
echo " " 

echo "Env:"
env

#Run building cloudformation
yes | python3.5 ./cloudformation.py create test.boss core --ami-version autotest
wait 
sleep 60
yes | python3.5 ./cloudformation.py post-init test.boss core --ami-version autotest
wait
sleep 30
yes | python3.5 ./cloudformation.py create test.boss redis --ami-version autotest
wait
yes | python3.5 ./cloudformation.py create test.boss api --ami-version autotest
wait
yes | python3.5 ./cloudformation.py create test.boss activities --ami-version autotest
wait
yes | python3.5 ./cloudformation.py create test.boss cloudwatch --ami-version autotest
wait
# yes  | python3.5 ./cloudformation.py create test.boss dynamolambda --ami-version autotest

echo " "
echo "----------------------Performing Tests----------------------"
echo " " 

#Perform tests on temporary test stacks

#Endpoint tests:
echo 'Performing tests...'
cd /srv/www/django
python3 manage.py test
python3 manage.py test -- -c inttest.cfg

#ndingest library
python3 -m pip install pytest
cd /usr/local/lib/python3/site-packages/ndingest
export NDINGEST_TEST=1
pytest -c test_apl.cfg
#Exit endpoint
exit

#cachemanage VM
cd /srv/salt/boss-tools/files/boss-tools.git/cachemgr
sudo nose2
sudo nose2 -c inttest.cfg
exit

echo " "
echo "----------------------Delete Stacks----------------------"
echo " " 

# yes | python3.5 ./cloudformation.py delete test.boss dynamolambda
# wait
yes | python3.5 ./cloudformation.py delete test.boss cloudwatch
wait
yes | python3.5 ./cloudformation.py delete test.boss activities
wait
yes | python3.5 ./cloudformation.py delete test.boss api
wait
yes | python3.5 ./cloudformation.py delete test.boss redis
wait
yes | python3.5 ./cloudformation.py delete test.boss core
wait

# echo " "
# echo "----------------------Cleanup environment----------------------"
# echo " " 

#Delete keypairs from aws
python3.5 ./manage_keypair.py delete auto-build-keypair
Shutdown the instance an hour after script executes.
shutdown -h +3600"""

    print('Running script...')
    instance = EC2.run_instances(
        ImageId=AMI,
        KeyName='microns-bastion20151117',
        SecurityGroupIds=[
            "sg-04bed83d9ddde98a1"
        ],
        InstanceType=INSTANCE_TYPE,
        MinCount=1,
        MaxCount=1,
        IamInstanceProfile={
            'Name': 'apl-ec2-auto-test',
        },
        InstanceInitiatedShutdownBehavior='terminate', # make shutdown in script terminate ec2
        UserData=init_script # file to run on instance init
    )
    instance_id = instance['Instances'][0]['InstanceId']
    
    tag = EC2.create_tags(
        Resources=[
            instance_id,
        ],
        Tags=[
            {
            'Key':'Name',
            'Value':'build.test.boss',
            },
        ],
        )
    print("New instance created.")
    print(instance_id)
    return(instance_id)
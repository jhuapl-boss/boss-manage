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

REGION = os.environ['AWS_REGION'] # region to launch instance leveraging lambda env var.
INSTANCE_TYPE = 't2.micro' # instance type to launch.

EC2 = boto3.client('ec2', region_name=REGION)

def lookup_ami(client):
    ami_names = ['lambda.boss', 'lambda.boss-h*']
    response = client.describe_images(Filters=[{"Name": "name", "Values": ami_names}])
    if len(response['Images']) == 0:
        raise Exception("Could not locate lambda.boss AMI")
    else:
        response['Images'].sort(key = lambda x: x['CreationDate'], reverse = True)
        ami = response['Images'][0]['ImageId']
        return ami


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

# Run this command before the `set -e`, as the set will
# cause the script to stop if the `command` returns non-zero
command -v apt-get >/dev/null; RET=$?

# Exit the script if any commands return a non-zero return value
set -e

if [ $RET -eq 0 ]; then
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

    PYTHON=python3.5
else
    yes | yum install jq
    yes | yum install git

    # Install the NodeJS Version Manager to install NodeJS as the system packages
    # are very out of date
    set +e
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.34.0/install.sh | bash
    export NVM_DIR="$HOME/.nvm"
    source $NVM_DIR/nvm.sh
    nvm install 8
    set -e

    # There seems to be an issue using the HTTPS version of the registry
    # and verifying the SSL certificate
    npm config set registry http://registry.npmjs.org/

    # The cracklib package has a symlink packer -> cracklib-packer
    # that will interfer with our use of Hashicorp's packer for building AMIs
    if [ -e /usr/sbin/packer ]; then
        rm /usr/sbin/packer
    fi

    cd /home/ec2-user

    # Current Lambda AMI contains Python 3.6 by default
    PYTHON=python3.6

    # PyMinifier is installed in /usr/local/bin, which is not part of
    # the PATH for the root user
    export PATH=${PATH}:/usr/local/bin
fi

# Download Packer
wget https://releases.hashicorp.com/packer/0.12.0/packer_0.12.0_linux_amd64.zip
unzip packer_0.12.0_linux_amd64.zip -d packer
wait
echo moving packer
sudo mv packer/packer /usr/bin/

#Clone github repo and install requirements
git clone https://github.com/jhuapl-boss/boss-manage.git
wait

#Checkout the right branch
cd boss-manage/
git checkout integration

#Install all requirements
git submodule init
git submodule update
$PYTHON -m pip install -r requirements.txt

# # Set-up log records on Cloudwatch:
# export EC2_REGION=`curl --silent http://169.254.169.254/latest/dynamic/instance-identity/document | jq -r .region`
# curl https://s3.amazonaws.com/aws-cloudwatch/downloads/latest/awslogs-agent-setup.py -O
# (echo
#  echo
#  echo
#  echo /var/log/cloud_init_output.log
#  echo 1
#  echo 1
#  echo N) | python3 ./awslogs-agent-setup.py --region $EC2_REGION

#Make vault private directory
mkdir vault/private

cd bin/

# Delete any existing test stack
echo " "
echo "----------------------Deleting Existing Stacks----------------------"
echo " "
yes | $PYTHON ./cloudformation.py delete auto-build-test.boss all

#Create  keypair to attach to ec2 instances made by cloudformation.
$PYTHON ./manage_keypair.py auto-build-test.boss delete auto-build-keypair
$PYTHON ./manage_keypair.py auto-build-test.boss create auto-build-keypair
wait

#Build AMIs
echo " "
echo "----------------------Building AMIs----------------------"
echo " "
$PYTHON ./packer.py auto-build-test.boss all --ami-version autotest --force
wait

echo " "
echo "----------------------Create Stack----------------------"
echo " "

echo "Env:"
env

#Run building cloudformation
yes | $PYTHON ./cloudformation.py create auto-build-test.boss all --ami-version autotest

wait

echo " "
echo "----------------------Performing Tests----------------------"
echo " "

# Disable error catching for tests, so that failed tests don't stop the script
set +e

#Perform tests on temporary test stacks

#Endpoint tests:
echo 'Performing tests...'
$PYTHON ./bastion.py endpoint.auto-build-test.boss ssh-cmd "sudo python3 -m pip install -r /srv/salt/spdb/files/spdb.git/requirements-test.txt"
$PYTHON ./bastion.py endpoint.auto-build-test.boss ssh-cmd "cd /srv/www/django && python3 manage.py test" # python3 manage.py test -- -c inttest.cfg

#ndingest library
$PYTHON ./bastion.py endpoint.auto-build-test.boss ssh-cmd "sudo python3 -m pip install pytest"
$PYTHON ./bastion.py endpoint.auto-build-test.boss ssh-cmd "cd /usr/local/lib/python3/site-packages/ndingest && export NDINGEST_TEST=1 && pytest -c test_apl.cfg"

#cachemanage VM
$PYTHON ./bastion.py cachemanager.auto-build-test.boss ssh-cmd "cd /srv/salt/boss-tools/files/boss-tools.git/cachemgr && sudo nose2 && sudo nose2 -c inttest.cfg"

set -e

echo " "
echo "----------------------Delete Stacks----------------------"
echo " "

yes | $PYTHON ./cloudformation.py delete auto-build-test.boss all
wait

# echo " "
# echo "----------------------Cleanup environment----------------------"
# echo " "

# Delete keypairs from aws
$PYTHON ./manage_keypair.py auto-build-test.boss delete auto-build-keypair

# Shutdown the instance an hour after script executes.
shutdown -h +3600"""

    print('Running script...')
    instance = EC2.run_instances(
        ImageId=lookup_ami(EC2),
        KeyName='microns-bastion20151117',
        SecurityGroupIds=[
            "sg-00d308289c6e2baac"
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

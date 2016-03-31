boss-manage
===========

This repository contains code for creating all of the infrastructure needed by
the [Boss](https://github.com/aplmicrons/boss) repository.

Components:

 * docs --- Instructions and tutorials
 * packer --- [Packer](https://www.packer.io/) configurations for building VM
              images populated with Salt
 * salt_stack --- [SaltStack](http://saltstack.com/) formulas for installing
                  and configuring software
 * cloud_formation --- Python scripts for creating AWS [CloudFormation](https://aws.amazon.com/cloudformation/)
                       templates, creating the CloudFormation Stacks, and
                       related helper functions
 * vault --- Python scripts for connecting to and managing [Vault](http://www.vaultproject.io/)
             instances used for storing secret information used by the other
             machines that make up the BOSS infrastructure.

## Getting Started

The Packer and CloudFormation scripts expect to be run from a machine with SSH
access to AWS. If you try to run this code from a location without this access
nothing will work.

## Python Libraries

The Vault and CloudFormation scripts make use of two Python libraries. To
install them run the following commands.

`pip3 install boto3`

`pip3 install hvac`

## Subrepositories

When building new machine images with Packer (either VBox or AWS AMI),
SaltStack expects the boss and boss-tools repositories to be checked
out to specific directories within the SaltStack directory structure.

Follow the directions in the [Submodules](docs/Submodules.md) help file to
correctly setup the submodules of boss-manage.

## SSH Keys

Currently the code that uses SSH tunnels creates SSH sessions is written
expecting an SSH client `ssh` to be in the system path.

When launching CloudFormation configurations the selected keypair will be used
when connecting to the Vault server. To make sure these connections are
successful make sure that the private key for the selected keypair exists as
`~/.ssh/<keypair>.pem` and has file permissions `400` / `-r--------`.

For the bastion.py and ssh.py scripts you need to either pass the keypair
file to use as a command line argument or you can export it as an environment
variable.

`export SSH_KEY=~/.ssh/<keypair>.pem`

## AWS Credentials

All of the scripts are written to make use of the same AWS credentials file,
so that they only need to be specified in one location. This file is the Packer
AWS credentials file (`packers/variables/aws-credentials.example`). If this
file contains your private and secret key then you can point the other scripts
(cloudformation.py, bastion.py, ssh.py) at it or you can export it as an
environment variable.

For example: `export AWS_CREDENTIALS=../packer/variables/aws-credentials`
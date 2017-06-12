boss-manage
===========

This repository contains code for creating all of the infrastructure needed by
the [Boss](https://github.com/aplmicrons/boss) repository.

Components:

 * docs --- Instructions and tutorials
 * bin --- Scripts and utilities for building / working with the BOSS infrastructure
 * lib --- Python libraries containing common code used by scripts and utilities
 * packer --- [Packer](https://www.packer.io/) configurations for building VM
              images populated with Salt
 * salt_stack --- [SaltStack](http://saltstack.com/) formulas for installing
                  and configuring software
 * cloud_formation --- Configuration files creating AWS [CloudFormation](https://aws.amazon.com/cloudformation/)
                       templates
 * vault --- [Vault](http://www.vaultproject.io/) private key / token storage
             and policies used for initial configuration of a Vault instance.

## Getting Started

The Packer and CloudFormation scripts expect to be run from a machine with SSH
access to AWS. If you try to run this code from a location without this access
nothing will work.

## Python Libraries

The Vault and CloudFormation scripts make use of two Python libraries. To
install them run the following commands.

`pip3 install -r requirements.txt`

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

**Note:** Relative file paths are from the location of the script being executed.

## Legal

Use or redistribution of the Boss system in source and/or binary forms, with or without modification, are permitted provided that the following conditions are met:
 
1. Redistributions of source code or binary forms must both retain any copyright notices and adhere to licenses for any and all 3rd party software (e.g. Apache).
2. End-user documentation or notices, whether included as part of a redistribution or disseminated as part of a legal or scientific disclosure (e.g. publication) or advertisement, must include the following acknowledgement:  The Boss software system was designed and developed by the Johns Hopkins University Applied Physics Laboratory (JHU/APL). 
3. The names “The Boss”, “JHU/APL”, “Johns Hopkins University”, “Applied Physics Laboratory”, “MICrONS”, or “IARPA” must not be used to endorse or promote products derived from this software without prior written permission. For written permission, please contact BossAdmin@jhuapl.edu.
4. This source code and library is distributed in the hope that it will be useful, but is provided without any warranty of any kind.



boss-manage
===========

This repository contains code for creating all of the infrastructure needed by
the [Boss](https://github.com/jhuapl-boss/boss) repository.

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

For full instructions on how to configure everything needed to get a Boss instance
running, read the [Install Guide](docs/InstallGuide.md).

## Python Libraries

The boss-manage scripts and utilities make use of a minimal number of 3rd party
Python3 libraries. To install them run the following command.

`pip3 install -r requirements.txt`

## Subrepositories

When building new AWS AMIs with Packer, SaltStack expects the boss and
boss-tools repositories to be checked out to specific directories within
the SaltStack directory structure.

Follow the directions in the [Submodules](docs/Submodules.md) help file to
correctly setup the submodules of boss-manage.

## SSH Keys

Currently the code that uses SSH tunnels creates SSH sessions is written
expecting an SSH client `ssh` to be in the system path.

When launching CloudFormation configurations the selected keypair will be used
when connecting to the Vault server. To make sure these connections are
successful make sure that the private key for the selected keypair exists as
`~/.ssh/<keypair>.pem` and has file permissions `400` / `-r--------`.

## AWS Credentials

AWS API keys are loaded using the boto3 profile name given in the Bosslet
configuration passed to the script / utility being executed.

## Bosslet Configuration

All boss-manage code makes use of a single configuration object, called a
bosslet config. The configuration object is based on a file created by the
user and containing all of the information describing the Boss instance that
should be created or acted upon.

For more information see [config/README.md](config/README.md)

## Legal

Use or redistribution of the Boss system in source and/or binary forms, with or without modification, are permitted provided that the following conditions are met:
 
1. Redistributions of source code or binary forms must adhere to the terms and conditions of any applicable software licenses.
2. End-user documentation or notices, whether included as part of a redistribution or disseminated as part of a legal or scientific disclosure (e.g. publication) or advertisement, must include the following acknowledgement:  The Boss software system was designed and developed by the Johns Hopkins University Applied Physics Laboratory (JHU/APL). 
3. The names "The Boss", "JHU/APL", "Johns Hopkins University", "Applied Physics Laboratory", "MICrONS", or "IARPA" must not be used to endorse or promote products derived from this software without prior written permission. For written permission, please contact BossAdmin@jhuapl.edu.
4. This source code and library is distributed in the hope that it will be useful, but is provided without any warranty of any kind.



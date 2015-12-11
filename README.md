boss-manage
===========

This repository contains code for creating all of the infrastructure needed by
the [BOSS](https://github.com/aplmicrons/boss) repository.

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
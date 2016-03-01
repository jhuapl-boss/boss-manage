Creating a new machine type
===========================

Intro
-----
When creating a new machine type for MICrONS there are several steps that need
to happen. All of these steps are applicable even if just updating an existing
machine type.

Before starting make sure you have boss-manage.git checked out and the followed
the instructions in the boss-manage.git README file for checking out the needed
subrepositories.

SaltStack
---------
SaltStack is used to define what software packages are installed on a machine.
The behavior of Salt is controlled by `salt_stack/salt/top.sls`. For a new
machine create a new top level entry and if updating an existing machine type
update it's top level entry.

For more information about SaltStack configuration look at the SaltStack
documentation and read existing Salt formulas.

**Note:** In most cases you will want to include the boss-tools.bossutils
formula. This includes the bossutils python library which supports connecting
with Vault and AWS as well as setting the hostname of the system.

Packer
------
Packer is used to build VM images (Virtualbox OVF or AWS AMI) that are
configured by SaltStack.

1. Create a new Packer variable file.
  1. Copy one of the existing files in `packer/variables/`
  2. Rename the new file with the name used in `top.sls`
  3. Edit the new file and update the name to the name used in `top.sls`
2. Follow the README in `packer/` for instructions on how to run Packer
to build the new AMI.

**Note:** AMIs are named as <name>.boss to make sure they are unique in AWS

**Note:** if you are rebuilding an existing machine image you can skip step #1.
Instead you need to log into the AWS EC2 console and under the AMIs section
deregister the existing AMI image that you are about to rebuild.

CloudFormation
--------------
The last step is to make use of the new AMI. Either you can add it to an
existing CloudFormation configuration or you can create a new CloudFormation
configuration. Both options are covered in NewCloudFormationConfiguration.
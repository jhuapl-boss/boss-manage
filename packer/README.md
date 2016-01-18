Packer
======

Used to create prepopulated VM images that can be used later. They are
prepopulated with software for specific roles, but machine specific information
(crypto keys for example) are set to be generated when the machine boots for
the first time.


default.packer
--------------
Used for local development and testing using VirtualBox. It creates an OVF
image using the Packer virtualbox-iso builder.  This minimal install
configures sudo to be passwordless and installs VirtualBox Guest Additions.

`packer build -var 'source=ubuntu-14.04.2-server-amd64' default.packer`


vm.packer
---------
Used to populate a VM image with software for a specific role and configure
firstboot generation of machine data. It defines Packer builders for both
virtualbox-ovf (which uses the OVF image created by default.packer) and
amazon-ebs (which creates a custom AMI image).

`packer build -only=virtualbox-ovf -var-file=variables/aws-credentials -var-file=variables/<machine-type> vm.packer`

`packer build -only=amazon-ebs -var-file=variables/aws-credentials -var-file=variables/<machine-type> vm.packer`

**Note:** variable files should not have '.' in the filename or the
          '-var-file=' ignores anything after the '.' and cannot locate the file

**Note:** AWS credentials are required even when only building for virtualbox,
          but the credentials variables can be empty.


Building VirtualBox Images
-------------------------
To build a virtual box OVF there are two parts. The first part it to install
Ubuntu using *default.packer*. First you need to download the [iso](http://releases.ubuntu.com/14.04.3/ubuntu-14.04.3-server-amd64.iso)
and put it in the *packer/files/*. Then run *default.packer* as described above.
This will install Ubuntu into an OVF that will then be configured as desired.
This was broken into two steps to make it quicker to iterate SaltStack and
other configuration changes.

Once default.packer completes and creates *output/virtualbox-default/virtualbox-default.ovf*
then you can populate it for a specific role. Create a variables file in
*packer/variables/* (if needed). Run *vm.packer* with the `-only=virtualbox-ovf`
option and it will take the OVF created by default.packer and produce a
populated / configured OVF in *output/virtualbox-<machine-type>/<machine-type>.ovf*.

**Note:** If there are problems with Packer saving the results, make sure the
          *output/* directory exists.

Vagrant
-------

Along with the VirtualBox image, a Vagrant box is also placed in the the
*output/* folder.  Vagrant is meant for developers and devOps work.  It
generates a reproducible development environment based on the a VM image.  It
was the first product to come out of Hashicorp (also the creators of Packer and
Vault).  Once the Vagrant box is configured, you simply type ````vagrant up````
to spin up your development environment.  

Vagrant automatically maps a shared folder */vagrant* to your working folder
(the location of the *Vagrantfile* config file) on your host machine, so you
can use your favorite editor.  A working *Vagrantfile* is included
in root folder of this repo.  It will start both an endpoint and vault instance
when you type ````vagrant up````.  To start one or the other, type
````vagrant up vault```` or ````vagrant up endpoint````.

To ssh into one of the Vagrant boxes, type ````vagrant ssh <box name>````.

To put a Vagrant box to sleep, type ````vagrant suspend <box name>````.

When you no longer need a Vagrant box or you want to start fresh, type ````vagrant destroy <box name>````.

See https://www.vagrantup.com for more information on Vagrant.

**Note:** If you end up regenerating the Vagrant box via Packer, be sure to
delete the cached version before running ````vagrant up```` again.  Otherwise,
you won't be using the latest version of the VM.  The cached version is stored
in *~/.vagrant.d/boxes/name-of-the-Vagrant-box*.


Building an AWS AMI
-------------------
To build an AWS AMI there is just a single step, as AWS already provides
baseline AMI images. Create a variables file in *packer/variables/* (if needed).
Run *vm.packer* with the `-only=amazon-ebs` option and it will take the baseline
AWS AMI and produce a populated / configured AMI that can be launched later.

If running **inside** the **APL firewall**, get the private key for the APL
bastion server and place it in the same folder as *vm.packer*. Include
````-var-file=variables/aws-bastion```` so Packer connects via the APL
bastion server.  Check variables/aws-bastion for the expected name of the
private key file.

**Note:** This requires your AWS credentials in the AWS variable file and access
          from the machine that is running packer to AWS.

**Example of building an endpoint server instance using the bastion server:**

````packer build -var-file=variables/my-aws-creds -var-file=variables/aws-bastion -var-file=variables/endpoint -only=amazon-ebs vm.packer````

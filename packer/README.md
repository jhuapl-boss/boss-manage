Packer
======

Used to create prepopulated VM images that can be used later. They are
prepopulated with software for specific roles, but machine specific information
(crypto keys for example) are set to be generated when the machine boots for
the first time.


default.packer
--------------
Used for local development and testing using VirtualBox. It creates an OVF
image using the Packer virtualbox-iso builder. The only modification that it
does to the stock minimal install is to configure sudo to be passwordless.

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


Builing VirtualBox Images
-------------------------
To build a virtual box OVF there are two parts. The first part it to install
Ubuntu using *default.packer*. First you need to download the [iso](http://releases.ubuntu.com/14.04.3/ubuntu-14.04.2-server-amd64.iso)
and put it in the *packer/files/*. Then run *default.packer* as described above.
This will install Ubuntu into an OVF that will then be configured as desired.
This was broken into two steps to make it quicker to itterate SaltStack and
other configuration changes.

Once default.packer completes and creates *output/virtualbox-default/virtualbox-default.ovf*
then you can populate it for a specific role. Create a variables file in
*packer/variables/* (if needed). Run *vm.packer* with the `-only=virtualbox-ovf`
option and it will take the OVF created by default.packer and produce a
populated / configured OVF in *output/virtualbox-<machine-type>/<machine-type>.ovf*.

**Note:** If there are problems with Packer saving the results, make sure the
          *output/* directory exists.


Building an AWS AMI
-------------------
To build an AWS AMI there is just a single step, as AWS already provides
baseline AMI images. Create a variables file in *packer/variables/* (if needed).
Run *vm.packer* with the `-only=amazon-ebs` option and it will take the baseline
AWS AMI and produce a populated / configured AMI that can be launched later.

**Note:** This requires your AWS credentials in the AWS variable file and access
          from the machine that is running packer to AWS.
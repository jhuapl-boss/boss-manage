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
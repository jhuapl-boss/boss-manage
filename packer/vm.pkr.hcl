# IP of the APL bastion server
variable "aws_bastion_ip" {
  type    = string
  default = ""
}

# Port on the APL bastion server
variable "aws_bastion_port" {
  type    = string
  default = "22"
}

# Path to the bastion's private key file
variable "aws_bastion_priv_key_file" {
  type    = string
  default = ""
}

# User name to login to the bastion server
variable "aws_bastion_user" {
  type    = string
  default = ""
}

variable "aws_instance_type" {
  type    = string
  default = "m4.large"
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "aws_source_ami" {
  type = string
}

variable "aws_source_user" {
  type = string
}

# Commit hash of the repository version being built from
variable "commit" {
  type    = string
  default = "unknown"
}

# Force the deregister of AWS AMIs
variable "force_deregister" {
  type    = string
  default = "false"
}

# The hostname and minion ID of the VM
variable "name" {
  type = string
}

# Common suffix for all AMI images
variable "ami_suffix" {
  type = string
}

# An optional suffix for the build name
variable "ami_version" {
  type    = string
  default = ""
}

source "amazon-ebs" "autogenerated_1" {
  ami_description              = "AMI configured for running as a / the ${var.name} server"
  # Using the 'ami_suffix' to make sure our names are unique in AWS
  ami_name                     = "${var.name}${var.ami_suffix}${var.ami_version}"
  force_deregister             = "${var.force_deregister}"
  instance_type                = "${var.aws_instance_type}"
  region                       = "${var.aws_region}"
  source_ami                   = "${var.aws_source_ami}"
  ssh_bastion_host             = "${var.aws_bastion_ip}"
  ssh_bastion_port             = "${var.aws_bastion_port}"
  ssh_bastion_private_key_file = "${var.aws_bastion_priv_key_file}"
  ssh_bastion_username         = "${var.aws_bastion_user}"
  ssh_username                 = "${var.aws_source_user}"
  tags = {
    "Base AMI" = "${var.aws_source_ami}"
    Commit     = "${var.commit}"
  }
}

build {
  sources = ["source.amazon-ebs.autogenerated_1"]

  provisioner "shell-local" {
    inline = ["tar -C ../salt_stack -czf /tmp/salt_files.tar.gz ./pillar ./salt"]
  }

  provisioner "shell" {
    # Update the hostname in /etc/hosts, /etc/hostname, and in memory
    # Install cURL so that salt-masterless can bootstrap Salt
    inline = ["sudo apt-get update",
              "sudo apt-get -y install curl"]
  }

  provisioner "file" {
     source = "/tmp/salt_files.tar.gz"
     destination = "/tmp/salt_files.tar.gz"
  }

  provisioner "file" {
     source = "../salt_stack/salt-bootstrap/bootstrap-salt.sh"
     destination = "/tmp/bootstrap-salt.sh"
  }

  provisioner "shell" {
    inline = ["sudo tar -C /srv -xf /tmp/salt_files.tar.gz",
              "sudo chmod +x /tmp/bootstrap-salt.sh",
              "echo sudo /tmp/bootstrap-salt.sh -i ${var.name} stable 3005.2",
              "sudo /tmp/bootstrap-salt.sh -i ${var.name} stable 3005",
              "echo sudo salt-call --local state.highstate --file-root=/srv/salt --pillar-root=/srv/pillar --id=${var.name}",
              "sudo salt-call --local state.highstate --file-root=/srv/salt --pillar-root=/srv/pillar --id=${var.name}",
              "echo deleting temp files from /tmp",
              "sudo rm /tmp/bootstrap-salt.sh /tmp/salt_files.tar.gz"]
  }

}
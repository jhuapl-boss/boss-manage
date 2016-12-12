Boss Manage Libraries
=====================

Table of Contents:

    * [aws.py](#aws.py)
    * [boto_wrapper.py](#boto_wrapper.py)
    * [cloudformation.py](#cloudformation.py)
    * [constants.py](#constants.py)
    * [exceptions.py](#exceptions.py)
    * [external.py](#external.py)
    * [hosts.py](#hosts.py)
    * [keycloak.py](#keycloak.py)
    * [names.py](#names.py)
    * [scalyr.py](#scalyr.py)
    * [ssh.py](#ssh.py)
    * [userdata.py](#userdata.py)
    * [utils.py](#utils.py)
    * [vault.py](#vault.py)
    * [zip.py](#zip.py)

aws.py
------
Collection of methods for looking up information in AWS.

Also contains a method to convert a dictionary or file handle
into a Boto3 session object.

boto_wrapper.py
---------------
Wrapper class around some Boto3 calls that makes error handling a little easier

cloudformation.py
-----------------
Library containing classes and methods used to build a CloudFormation template
and Create / Update / Delete it.

constants.py
------------
Library of constants used by the different cloud_formation scripts. From file
locations and Vault paths to EC2 instance types and cluster sizes.

exceptions.py
-------------
Custom exceptions used by libraries.

external.py
-----------
Library for use by cloud_formation script to connect to the different EC2
machines / services and configure them for operations.

hosts.py
--------
Library containing information for calculating IP subnets for VPCs and Subnets.

keycloak.py
-----------
Library for connecting to and configuring Keycloak.

names.py
--------
Library of resource names, reducing the number of `+ '.' + domain` statements
appear in cloud_formation configs and making sure all configs have the same
resource reference.

scalyr.py
---------
Library for configuring Scalyr monitoring of EC2 instances.

ssh.py
------
Library containing methods for creating SSH tunnels and SSHConnection class
to facilitate the different SSH connection types.

userdata.py
-----------
Library for parsing default boss.config file and populating it for use by an
EC2 instance.

utils.py
--------
Misc functions

vault.py
--------
Library of logic to connect to a Vault instance and manipulate it.

zip.py
------
Library of methods for zipping up files into a single archive.

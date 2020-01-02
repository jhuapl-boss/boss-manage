Boss Manage Libraries
=====================

Table of Contents:

* [aws.py](#awspy)
* [boto_wrapper.py](#boto_wrapperpy)
* [cloudformation.py](#cloudformationpy)
* [constants.py](#constantspy)
* [configuration.py](#configurationpy)
* [console.py](#consolepy)
* [datapipeline.py](#datapipelinepy)
* [exceptions.py](#exceptionspy)
* [external.py](#externalpy)
* [hosts.py](#hostspy)
* [keycloak.py](#keycloakpy)
* [lambdas.py](#lambdaspy)
* [migrations.py](#migrationspy)
* [names.py](#namespy)
* [stepfunctions.py](#stepfunctionspy)
* [ssh.py](#sshpy)
* [userdata.py](#userdatapy)
* [utils.py](#utilspy)
* [vault.py](#vaultpy)
* [zip.py](#zippy)


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

configuration.py
----------------
Library for loading and verifying a Bosslet configuration object. Once loaded
commonly used library references (like names.AWSNames) will be loaded and
made available via the Bosslet configuration object.

console.py
----------
Library for interacting with the console / the user. Includes methods for
displaying methods, prompting the user to answer a question, and a methods for
displaying a status bar.

All methods correctly handle if stdin or stdout are not connected to a terminal
(if they are redirected).

datapipeline.py
---------------
Library for building DataPipeline templates. Templates can either be created to
be embedded in a CloudFormation template or to be used directly in calls to
AWS DataPipeline.

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

lambdas.py
----------
Library of methods for interacting with AWS Lambda functions and building
their code zip files.

migrations.py
-------------
Library containing logic for calculating which migration files to execute when
performing a CloudFormation update.

names.py
--------
Library of resource names, reducing the number of `+ '.' + domain` statements
appearing in cloud_formation configs and making sure all configs have the same
resource reference.

stepfunctions.py
----------------
Library for working with AWS StepFunctions and wraps calls to Heaviside for
compiling the boss-manage Heaviside files into StepFunction definitions.

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

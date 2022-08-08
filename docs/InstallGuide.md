# BOSS Install Guide

This install guide is designed to guide someone who is setting up a new AWS
account and checking out the source code for the first time.

*Note on style: Any reference to “boss-manage.git/” is a reference to the root
directory of the cloned boss-manage.git repository.*

*Note on style: Unless otherwise noted all shell commands are expected to be run
from the root directory of the cloned boss-manage.git repository.*

## Requirements

### Workstation
You will need a machine installed with the following software packages:
* Python 3.5 or later
  - The Boss Manage software can be run within `venv`, `virtualenv`, or `virtualenvwrapper`
* Packer ([download](https://www.packer.io/)) (add it to your path or in the `boss-manage.git/bin/` directory)

Note: The boss-manage software was developed and tested under Linux and Mac. It has not been tested under Windows, including under Windows Subsystem for Linux.

#### Lambda Build
There are multiple ways to build the lambda code zip files. The standard way is to use an EC2 instance, but the boss-manage code supports building locally using Docker or directly on the machine running the boss-manage code

Requirements for Docker:
* Docker or Docker CLI compatible container environment (like Podman)
* Set the environment variable `LAMBDA_BUILD_CONTAINER` to the name of the container command
  - `export LAMBDA_BUILD_CONTAINER=docker`
  - Or in the Bosslet config `os.environ['LAMBDA_BUILD_CONTAINER'] = 'docker'`

Requirements for Local Machine:
* NodeJS ([download](https://nodejs.org/en/download/)) Version 10.X
* Yum package manager
  - Lambdas run on Amazon Linux, which is a Red Hat derivative distribution

## Clone Repositories
You will need access to the following code repositories on Github:
* [boss-manage.git](https://github.com/jhuapl-boss/boss-manage)
* [boss-tools.git](https://github.com/jhuapl-boss/boss-tools)
* [boss.git](https://github.com/jhuapl-boss/boss)
* [spdb.git](https://github.com/jhuapl-boss/spdb)
* [ndingest.git](https://github.com/jhuapl-boss/ndingest)
* [ingest-client.git](https://github.com/jhuapl-boss/ingest-client)
* [heaviside.git](https://github.com/jhuapl-boss/heaviside.git)

To clone these repositories run

```shell
$ git clone --recursive https://github.com/jhuapl-boss/boss-manage.git
```

The `--recursive` flag tells git to initalize and update the [git submodules](https://git-scm.com/book/en/v2/Git-Tools-Submodules) that link the boss-manage repository to the other repositories.

To update the boss-manage code and its submodule references run

```shell
$ git pull
$ git submodule update
```

### Install requirements
To install the Python packages needed for boss-manage to work, run

```shell
pip install -r requirements.txt
```

## Setup AWS Account
If this is the first time you will be launching a bosslet into an AWS account, run through the instructions in [InitialAwsSetup.md](InitialAwsSetup.md) to configure it to be ready to launch the bosslet.

## Setup Boss Dependencies
If this is the firest time you will be launching the bosslet, run through the instructions in [InitialBossSetup.md](InitialBossSetup.md) to configured the external dependencies needed for a bosslet.

## Create Bosslet config
If you didn't run the **Setup AWS Account** step, create a bosslet config following the [Create Bosslet Config](InitialAwsSetup.md#Create-Bosslet-Config) in the [InitialAwsSetup.md](InitialAwsSetup.md) document.

## Create AMIs
Several AWS Images (AMIs) need to be created. These images are preconfigured for
specific roles within the architecture. These procedures expect the AWS
credentials and AWS bastion files described in the previous two sections.

Make sure that the Packer executable is either in $PATH (you can call it by just
calling packer) or in the `bin/` directory of the boss-manage repository.

```shell
$ bin/packer.py <bosslet_config> all
```

*Note: because the packer.py script is running builds in parallel it is redirecting
the output from each Packer subprocess to `packer/logs/<config>.log`. Because of
buffering you may not see the file update with every new line. Tailing the log
does seem to work (`tail -f packer/logs/<config>.log`)*
Check for Success or failure with the command below:
```shell
$ grep "artifact" ../packer/logs/*.log
```

Success looks like this:
==> Builds finished. The artifacts of successful builds are:
Failure like this
==> Builds finished but no artifacts were created.

It can beneficial to check the logs before all the AMIs are completed, 
when issues do occur, they frequently fail early.  Discovering this 
allows you to relauch packer.py in another terminal for the failed AMIs,
saving time overall.

## Launching configs
The full Boss system consists multiple CloudFormation templates that build upon each other to provide the full set of capabilities. To launch a fully functional system run the following command, which will launch each of the templates in succession.

*Note: If you are building a production level system added the `--scenario production` to the command, or set the `SCENARIO` variable in the Bosslet config. By default the cloudformation.py script will create the Boss resources with the minimal instance sizes available.*
```shell
$ bin/cloudformation.py create <bosslet_config> core redis api cachedb activities cloudwatch
```

*Note: The cloudformation.py script will automatically use the latest created AMIs
that are named with a commit hash. Since you just rebuilt the AMIs they should be
the latest ones.*

### Setting Up Web Page
Create a S3 bucket named: **www.theboss.io**
Under propertes of the bucket in the **Static Website Hosting** section
click **Enable Website Hosting**
Index Document: index.html
Redirect rules should have
```
<RoutingRules>
    <RoutingRule>
        <Redirect>
            <Protocol>http</Protocol>
            <HostName>docs.theboss.io</HostName>
            <ReplaceKeyPrefixWith/>
            <HttpRedirectCode>301</HttpRedirectCode>
        </Redirect>
    </RoutingRule>
</RoutingRules>
```

Under Route53 two CNAME records in the hosted zone theboss.io 
1. docs.theboss.io 
    * the web server hosting theboss documentation.
2. www.theboss.io
    * the S3 bucket name which is currently:
    * www.theboss.io.s3-website-us-east-1.amazonaws.com

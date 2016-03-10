Boss Manage Utilities
=====

This directory contains different utilities for building and interacting with
the BOSS infrastructure.

packer.py
---------
Used to simplify the building of machine images using [Packer]() and [SaltStack]().
The scrpt tags built AWS AMIs with the commit version and it can build multiple
images at the same time.

Requirements:

* git - Should be installed under $PATH or in the boss-manage.git/bin/ directory
* packer - Should be installed under $PATH or in the boss-manage.git/bin/ directory
* microns bastion private key - Should be in the same directory as the packer binary

Important Arguments:

* `-h` will display a full help message with all arguments
* `--name` will name the built AMI. By default the first 8 characters of the
  commit hash are used. A name can be something like "production", "integration",
  "test", or your username. If the name "test" is used it also implies that any
  existing AMI with the same name will be deregistered first. (making it easier
  to test builds of a machine)
* `<config>` is the name of a Packer variable file under `packer/variables/` to
  build. Multiple config file names can be given, or "all" will build every file
  in `packer/variables/`

When passing multiple config names to the script, it will build them all in
parallel. The output from each build will be sent to the log file `packer/logs/<config>.log`.
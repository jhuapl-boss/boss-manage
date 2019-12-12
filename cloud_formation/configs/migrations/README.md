# CloudFormation Update Migrations
There are times when a CloudFormation update requires code to execute before and/or after the CloudFormation update happens. To support this the Boss CloudFormation templates include the `StackVersion` tag, which contains the version number of the currently deployed template. If there are changes made to a template that require external code to run the version number is updated and a migration file can be written. The migration file will automatically execute, but only when the template's version changes. This allows for tracking this conditional code in git and without complicating the config file that generates the template.

## Creating a migration
If you make a change to template's config that requires a one time externally executed change follow the following steps:

 1. In the config file, when creating the `CloudFormationConfiguration` object increment the `version` argument by one. (If there is not a `version` argument add `version="2"` to the call)
 2. At the top of the config file add an entry to the `MIGRATION CHANGELOG` list. (If there is not a changelog, create one in the top level commend for the config and include `Version 1: Initial version of config` as the first entry)
 3. Create the following file `cloud_formation/configs/migrations/<config>/AAAABBBB_short_name.py`
    * `<config>` is the name of the config passed to the `CloudFormationConfiguration` object
    * `AAAA` is the previous version number, zero padded to 4 characters
    * `BBBB` is the new version number, zero padded to 4 characters
    * `short_name` is a short descriptor that will be printed for the user when a pre or post update migration will be executed
 4. In the new migration file you can define `def pre_update(bosslet_config):` and/or `def post_update(bosslet_config):`
    * You can import any `boss-mange` libraries like normal (`from lib import constants as const`, etc)
    * Migrations should be able to be run multiple times in the case of errors occurring
    * If there are errors in the `post_update` migration(s) being applied, an error message should be printed so the user knows what to do to fix the problem
    * If there are errors in the `post_update` migration(s) being applied, the user can run `bin/cloudformation.py update-migrate <bosslet> <config>` to re-run the failed `post_update` migration and any other `post_update` migration(s) that still need to be applied
    * `pre_update` migrations can confirm that the user want to make the change using `lib.console.confirm()` and raising `lib.exceptions.BossManageCanceled` if they don't confirm

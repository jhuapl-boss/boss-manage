# MICrONS Merge and Tag Guide

This guide is written expecting the branching model for MICrONS, where there is
an integration branch for each sprint where development occurs (or developer
branches which are merged into the integration branch). This guide documents the
steps needed to merge the integration branch into the master (stable) branch and
tag the release.


## Tagging the end of a sprint

### Submodule Repositories
For each of the following repositories
* https://github.com/aplmicrons/boss.git
* https://github.com/aplmicrons/proofread.git
* https://github.com/aplmicrons/boss-tools.git
* https://github.com/aplmicrons/spdb.git
* https://github.com/jhuapl-boss/ingest-client
* https://github.com/jhuapl-boss/ndingest
* https://github.com/jhuapl-boss/intern.git (intern is not a sub-module, but also needs tagging)
* https://github.com/jhuapl-boss/ingest_test.git (not a sub-module, but also needs tagging)


If you don't have the repository already cloned
```shell
$ git clone <url>
$ cd <repository>
```

To create the tag
```shell
$ git checkout integration
$ git pull # if you didn't need to clone
$ git tag sprint#
$ git push origin sprint#
```


### Boss-manage Repository
If you don't have the repository already cloned
```shell
$ git clone --recursive https://github.com/aplmicrons/boss-manage.git
$ cd boss-manage
```

To create the tag
```shell
$ git checkout integration
$ git pull # if you didn't need to clone
$ git submodule update --remote
$ git add salt_stack/salt/boss/files/boss.git
$ git add salt_stack/salt/boss-tools/files/boss-tools.git
$ git add salt_stack/salt/proofreader-web/files/proofread.git
$ git add salt_stack/salt/spdb/files/spdb.git
$ git add salt_stack/salt/ndingest/files/ndingest.git
$ git add salt_stack/salt/ingest-client/files/ingest-client.git
# Review the SHA hash for each submodule to make sure it correctly points to the
#   tagged version
$ git commit -m "Updated submodule references"
$ git tag sprint#
$ git push --tags
$ git push
```

## Tagging a stable release

### Submodule Repositories
For each of the following repositories
* https://github.com/aplmicrons/boss.git
* https://github.com/aplmicrons/proofread.git
* https://github.com/aplmicrons/boss-tools.git
* https://github.com/aplmicrons/spdb.git
* https://github.com/jhuapl-boss/ingest-client
* https://github.com/jhuapl-boss/ndingest
* https://github.com/jhuapl-boss/intern.git (intern is not a sub-module, but also needs tagging)
* https://github.com/jhuapl-boss/ingest_test.git (not a sub-module, but also needs tagging)


If you don't have the repository already cloned
```shell
$ git clone <url>
$ cd <repository>
```

To create the tag
```shell
$ git fetch # if you didn't need to clone
$ git checkout master
$ git merge integration # resolve any conflicts and commit
$ git tag <release#>
$ git push --tags
$ git push  # One more push to push the merged commits.
```


### Boss-manage Repository
If you don't have the repository already cloned
```shell
$ git clone --recursive https://github.com/aplmicrons/boss-manage.git
$ cd boss-manage
```

To create the tag
```shell
$ git fetch # if you didn't need to clone
$ git checkout master
$ git merge integration # resolve any conflicts and commit
$ EDITOR .gitmodules # update referenced branches to master
$ git add .gitmodules
$ git submodule foreach "git fetch && git checkout tags/<release#>"
$ git add salt_stack/salt/boss/files/boss.git
$ git add salt_stack/salt/boss-tools/files/boss-tools.git
$ git add salt_stack/salt/proofreader-web/files/proofread.git
$ git add salt_stack/salt/spdb/files/spdb.git
$ git add salt_stack/salt/ndingest/files/ndingest.git
$ git add salt_stack/salt/ingest-client/files/ingest-client.git
# Review the SHA hash for each submodule to make sure it correctly points to the
#   tagged version
$ git commit -m "Updated submodule references"
$ git tag <release#>
$ git push --tags
$ git push
```

## Building tagged AMIs

To create AMIs for a specific version of repository code. All AMIs will be built
in parallel. To check status view the logs at `boss-manage/packer/logs/<ami>.log`

```shell
$ cd boss-manage
$ bin/packer.py auth vault consul endpoint proofreader-web cachemanager --name <sprint#|release#>
$ cd ../packer
$ packer build -var-file=../config/aws-credentials -var-file=variables/lambda -var-file=../config/aws-bastion -var 'name_suffix=<sprint#|release#>' -var 'force_deregister=true' lambda.packer
```

# MICrONS Merge and Tag Guide

This guide is written expecting the branching model for MICrONS, where there is
an integration branch for each sprint where development occurs (or developer
branches which are merged into the integration branch). This guide documents the
steps needed to merge the integration branch into the master (stable) branch and
tag the release.


## Tagging the end of a sprint

### Submodule Repositories
For each of the following repositories
* https://github.com/jhuapl-boss/boss.git
* https://github.com/jhuapl-boss/boss-tools.git
* https://github.com/jhuapl-boss/spdb.git
* https://github.com/jhuapl-boss/ingest-client
* https://github.com/jhuapl-boss/ndingest
* https://github.com/jhuapl-boss/heaviside
* https://github.com/jhuapl-boss/dynamodb-lambda-autoscale
* https://github.com/jhuapl-boss/intern.git (not a sub-module, but also needs tagging)
* https://github.com/jhuapl-boss/ingest_test.git (not a sub-module, but also needs tagging)
* https://github.com/jhuapl-boss/boss-oidc.git (not a sub-module, but also needs tagging)
* https://github.com/jhuapl-boss/django-oidc.git (not a sub-module, but also needs tagging)
* https://github.com/jhuapl-boss/drf-oidc-auth.git (not a sub-module, but also needs tagging)


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

### Updating tags
If you make any mistakes along the way and need to update where tags are pointing to 
use these two commands:
```shell
git tag -f -a <tagname>
git push -f --tags
```

### Boss-manage Repository
If you don't have the repository already cloned
```shell
$ git clone --recursive https://github.com/jhuapl-boss/boss-manage.git
$ cd boss-manage
```

To create the tag
```shell
$ git checkout integration
$ git pull # if you didn't need to clone
$ git submodule update --remote
$ git add salt_stack/salt/boss/files/boss.git
$ git add salt_stack/salt/boss-tools/files/boss-tools.git
$ git add salt_stack/salt/spdb/files/spdb.git
$ git add salt_stack/salt/ndingest/files/ndingest.git
$ git add salt_stack/salt/ingest-client/files/ingest-client.git
$ git add cloud_formation/lambda/dynamodb-lambda-autoscale
$ git add lib/heaviside.git
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
* https://github.com/jhuapl-boss/boss.git
* https://github.com/jhuapl-boss/proofread.git
* https://github.com/jhuapl-boss/boss-tools.git
* https://github.com/jhuapl-boss/spdb.git
* https://github.com/jhuapl-boss/ingest-client
* https://github.com/jhuapl-boss/ndingest
* https://github.com/jhuapl-boss/heaviside
* https://github.com/jhuapl-boss/dynamodb-lambda-autoscale
* https://github.com/jhuapl-boss/intern.git (not a sub-module, but also needs tagging)
* https://github.com/jhuapl-boss/ingest_test.git (not a sub-module, but also needs tagging)
* https://github.com/jhuapl-boss/boss-oidc.git (not a sub-module, but also needs tagging)
* https://github.com/jhuapl-boss/django-oidc.git (not a sub-module, but also needs tagging)
* https://github.com/jhuapl-boss/drf-oidc-auth.git (not a sub-module, but also needs tagging)

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
$ git clone --recursive https://github.com/jhuapl-boss/boss-manage.git
$ cd boss-manage
```

To create the tag
```shell
export RELEASE=<release#>
git fetch # if you didn't need to clone
git checkout master
git merge integration # resolve any conflicts and commit
EDITOR .gitmodules # update referenced branches to master
git add .gitmodules
# cut and paste the commands below as it much faster that way.  can't use "foreach" anymore because heaviside doesn't get same release numbers.
git -C lib/heaviside.git checkout master
git -C lib/heaviside.git pull
git -C dynamodb-lambda-autoscale checkout tags/$RELEASE
git -C salt_stack/salt/boss-tools/files/boss-tools.git checkout tags/$RELEASE
git -C salt_stack/salt/boss/files/boss.git checkout tags/$RELEASE
git -C salt_stack/salt/ingest-client/files/ingest-client.git checkout tags/$RELEASE
git -C salt_stack/salt/ndingest/files/ndingest.git checkout tags/$RELEASE
git -C salt_stack/salt/spdb/files/spdb.git tags/$RELEASE

git add salt_stack/*
# Review the SHA hash for each submodule to make sure it correctly points to the
#   tagged version
git submodule foreach "git status"
# Compare with the actual repos using this command, in actual repo
git log --pretty=format:'%h' -n 1
git commit -m "Updated submodule references"
git tag $RELEASE
git push --tags
git push
```

## Building tagged AMIs

To create AMIs for a specific version of repository code. All AMIs will be built
in parallel. To check status view the logs at `boss-manage/packer/logs/<ami>.log`

```shell
$ cd boss-manage
$ bin/packer.py auth vault endpoint cachemanager activities --name <sprint#|release#>
$ cd ../packer
$ packer build -var-file=../config/aws-credentials -var-file=variables/lambda -var-file=../config/aws-bastion -var 'name_suffix=<sprint#|release#>' -var 'force_deregister=true' lambda.packer
```


# Updating Public Facing Tools

We use pypi to provide pip-install capability from some of our tools. The packages are published under the username `jhuapl-boss`.


## intern

### Build docs
We use a simple tool called pdoc to generate basic auto-documentation for intern. These docs are hosted on GitHub pages automatically at [https://jhuapl-boss.github.io/intern/](https://jhuapl-boss.github.io/intern/)

To build the docs you need to first install pdoc into your virtualenv. I'm pretty sure this needs to be a 2.7 virtualenv.

```
deactivate
mkvirtualenv --python=`which python` intern-pypi
cd intern.git
pip install -r docs_requirements.txt
pip install -r requirements.txt
```

Then build the new docs

If you don't already have a PYTHONPATH just use this export instead of the line in the box:
   export PYTHONPATH=/<path to intern>
Otherwise it will fail with no error because the leading colon:  PYTHONPATH=:<path to intern>

```
cd intern.git
export PYTHONPATH=$PYTHONPATH:/<path to intern>
pdoc intern --html --html-dir="docs" --overwrite --docstring-style=google
mv ./docs/intern/* ./docs/
rm -rf ./docs/intern
```

Then commit the changes. Whenever the changes make it to `master`, the docs will be updated on the hosted GitHub pages site.

### Push to pip
Once you are ready to update pip you need to change the version, build, and upload.

0) Make sure you have twine installed in your virtualenv

```
pip install twine
```

1) Edit `intern.git/intern/__init__.py` and set `__version__` to the desired version

2) Build

```
cd intern.git
python setup.py sdist
python setup.py bdist_wheel
```

3) Upload to pip. `--skip-existing` is required now and twine will only  push versions that don't already exist in PyPi.

```
twine upload --skip-existing dist/*

```


## ingest-client

### Push to pip

Once you are ready to update pip you need to change the version, build, and upload.

0) Make sure you have twine installed in your virtualenv

```
pip install twine
```

1) Edit `ingest-client/ingestclient/__init__.py` and set `__version__` to the desired version

2) Build

```
cd ingest-client
python setup.py sdist
python setup.py bdist_wheel
```

3) Upload to pip. `--skip-existing` is required now and twine will only  push versions that don't already exist in PyPi.

```
twine upload --skip-existing dist/*
```

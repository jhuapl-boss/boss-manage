# Boss Testing Guide
This document covers running unit tests and integration tests within an existing Bosslet.


### Copy up dynamo information in spdb for testing
Now the spdb is a pypi installable it doesn't include the contents of 
spdb/spdb/spatialdb/dynamo/
You need to tar up the contents of that directory and use ssh-tunnel to copy it to the endpoint for testing
```bash
$ cd spdb/spdb/spatialdb
$ tar czf /path/to/spdb-spatialdb-dynamo.tar.gz ./dynamo
$ cd spdb
$ tar rzf /path/to/spdb-spatialdb-dynamo.tar.gz ./requirements-test.txt
```
 
To ssh tunnel:
```bash
$ boss-manage/bin/bastion.py endpoint.hiderrt1.boss ssh-tunnel
```
Connect to localhost:31812 to be forwarded to 10.104.4.18:22

To scp file after tar:
```.bash
$ scp -P 31812 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no /path/to/spdb-spatialdb-dynamo.tar.gz ubuntu@localhost:
```

then untar contents into:
**/usr/local/lib/python3.5/site-packages/spdb/spatialdb**
```bash
$ cd /usr/local/lib/python3.5/site-packages/spdb/spatialdb
$ tar xf ~/spdb-spatialdb-dynamo.tar.gz
$ pip3 install -r requirements-test.txt
```

### Use Test script
If you want to automate the testing of the following
* Endpoint Unit Testing
* Endpoint Integration Testing
* SPDB Integration Tests
* Test the ndingest library

cut and paste the following into a test.sh script on the endpoint.
```bash
#!/usr/bin/env bash

read -n 1 -p "running in screen?, if not ctrl-c to stop: "
echo press ctrl-A D if you want to detach from screen

export RUN_HIGH_MEM_TESTS=true
cd /srv/www/django
sudo -E python3 manage.py test 2>&1 | tee /home/ubuntu/1_django_unittest.txt

cd /srv/www/django
sudo -E python3 manage.py test -- -c inttest.cfg 2>&1 | tee /home/ubuntu/2_django_inttest.txt

cd /usr/local/lib/python3.5/site-packages/spdb
sudo nose2 2>&1 | tee /home/ubuntu/3_spdb_unittest.txt
sudo nose2 -c inttest.cfg 2>&1 | tee /home/ubuntu/4_spdb_inttest.txt

# Manual install for now.  Will likely remove use of pytest in the future.
sudo -H pip3 install pytest
cd /usr/local/lib/python3/site-packages/ndingest
# Use randomized queue names and prepend 'test_' to bucket/index names.
export NDINGEST_TEST=1
pytest -c test_apl.cfg 2>&1 | tee /home/ubuntu/5_ndingest_test.txt
```
now look over the log files in the home directory.

## Unit Testing

### Run unit tests on Endpoint
If you are following these instructions for your personal development environment, skip the
export RUN_HIGH_MEM_TESTS line.  That line runs 2 tests that need >2.5GB of memory
to run and will fail in your environment

```shell
cd bin
./bastion.py endpoint.integration.boss ssh
export RUN_HIGH_MEM_TESTS=True
cd /srv/www/django
sudo -E python3 manage.py test
```
	output should say Ran XXX tests.
If the number changes often, the important part is that none of the tests should fail.


## Integration Testing

### Endpoint Integration Tests

#### Test While Logged Onto the Endpoint VM
Again, Skip the RUN_HIGH_MEM_TESTS line below if you are following these instructions for
your personal development environment.  That line runs 2 tests that need >2.5GB
of memory to run and will fail in your environment

```shell
export RUN_HIGH_MEM_TESTS=True
cd /srv/www/django
sudo -E python3 manage.py test -- -c inttest.cfg
```
	output should say 55 Tests OK with 7 skipped tests

#### SPDB Integration Tests 
```shell
cd /usr/local/lib/python3.5/site-packages/spdb
sudo nose2
sudo nose2 -c inttest.cfg
```

##### Test the ndingest library.
```shell
# Manual install for now.  Will likely remove use of pytest in the future.
sudo pip3 install pytest
cd /usr/local/lib/python3/site-packages/ndingest
# Use randomized queue names and prepend 'test_' to bucket/index names.
export NDINGEST_TEST=1
pytest -c test_apl.cfg
```

### Cachemanager Integration Tests

#### Test While Logged Onto the Cachemanager VM

```shell
cd /srv/salt/boss-tools/files/boss-tools.git/cachemgr
sudo nose2
sudo nose2 -c inttest.cfg
```
	there is currently issues with some of the tests not getting setup correctly. cache-DB and cache-state-db need to be manutally set to 1.
	or the tests hang.

#### Test Using Intern From a Client

intern integration tests should be run from your local workstation or a VM
**not** running within the integration VPC.

First ensure intern is current:

```shell
# Clone the repository if you do not already have it.
git clone https://github.com/jhuapl-boss/intern.git

# Otherwise update with `pull`.
# git pull

# Make the repository the current working directory.
cd intern

# Check out the integration branch.
# If there is no current integration branch, use master.
git checkout integration

# Ensure dependencies are current.
sudo pip3 install -r requirements.txt
```

In your browser, open https://api.theboss.io/vX.Y/mgmt/token

Your browser should be redirected to the KeyCloak login page.

Create a new account and return to the token page.

Generate a token.

This token will be copied-pasted into the intern config file.

```shell
mkdir ~/.intern
EDITOR ~/.intern/intern.cfg
```

In your text editor, copy and paste the text config values below. Replace all
all tokens with the token displayed in your browser.

```
[Project Service]
protocol = https
host = api.theboss.io
# Replace with your token.
token = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

[Metadata Service]
protocol = https
host = api.theboss.io
# Replace with your token.
token = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

[Volume Service]
protocol = https
host = api.theboss.io
# Replace with your token.
token = xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Additionally, create a copy of `~/.intern/intern.cfg` as `test.cfg` in the intern
repository directory.

##### Setup via the Django Admin Page

In your browser, go to https://api.theboss.io/admin

Login using the bossadmin account created previously (this was created during
the endpoint initialization and unit test step).

Click on `Boss roles`.

Click on `MANAGE ROLES`.

Find the user you created and add the `user-manager` and `resource-manager` roles to that user and save.

Next login as that user so the new roles are properly synced.


##### Run Intern Integration Tests

Finally, open a shell and run the integration tests:

```shell
# Go to the location of your cloned intern repository.
cd intern.git
python3 -m unittest discover -p int_test*
```

Output should say:

```
Ran x tests in x.xxxs.

OK
```

#### Run Ingest Tests

* cd ingest-test
* run python3 ./setup_test.py
* Copy the export and and ingest run commands 
* cd ../ingest-client
* paste the copied commands above.
    this should start loading the ingest data
* cd back to the ingest-test directory
* python3 validate_ingest.py

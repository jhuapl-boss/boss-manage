# Django Local Development

This document shows how to set up your local machine for development with
Django.  Major steps are MySQL installation and initial setup as well as
Keycloak installation and setup.

These directions assume macOS.

## MySQL Setup

```shell
# Install mysql
brew install mysql

# Set the root password to what's defined in boss/django/settings/mysql.py
# You can say no to the other options or Ctrl-C to exit early.
mysql_secure_installation

# This command starts mysql (I don't normally leave it running)
mysql.server start

# Login to the DB
mysql -h localhost -u root -p
```

From the `mysql>` prompt:

```sql
% Create the initial DB
create database microns;

% Use Ctrl-D to exit
```

## Django Database Creation

```shell
# From the root of the boss repo:
cd django

# Until we get all our repos installable via pip, we can use PYTHONPATH to find
# them.  Adjust this line to match your system
export PYTHONPATH=~/Documents/MICrONS/spdb:~/Documents/MICrONS/ndingest:~/Documents/MICrONS/boss-manage/lib/heaviside.git:~/Documents/MICrONS/boss-tools:~/Documents/MICrONS/cvdb

# Make the boss log folder
sudo mkdir /var/log/boss

# And change it to your user name, so you don't need to run with sudo
sudo chown <your user name> /var/log/boss

python manage.py makemigrations --settings boss.settings.keycloak
python manage.py migrate --settings boss.settings.keycloak
```

## Keycloak Setup

Keycloak performs authentication for the Boss.  We can run Keycloak locally with
Docker.

If this document goes out of date, use `boss-manage/salt_stack/salt/keycloak/init.sls`
as the source of truth for setting up Keycloak locally.

Download Docker Desktop:
* Mac: https://docs.docker.com/docker-for-mac/release-notes/ 
* Windows: https://docs.docker.com/docker-for-windows/release-notes/ 

Download Keycloak: https://downloads.jboss.org/keycloak/11.0.3/keycloak-11.0.3.tar.gz

Uncompress Keycloak:

```shell
# This will uncompress Keycloak in your current folder in a subfolder called
# keycloak-11.0.3
tar xzf keycloak-11.0.3.tar.gz
```

Copy files from our Keycloak deployment to the new Keycloak folder:

```shell
# Replace <path to> with the path to your boss-manage folder
cd <path to>/boss-manage/salt_stack/salt/keycloak/files

# Set this to where you uncompressed Keycloak to
export KEYCLOAK_PATH=<path to>/keycloak-11.0.3

cp standalone.xml ${KEYCLOAK_PATH}/standalone/configuration
mkdir -p ${KEYCLOAK_PATH}/modules/system/layers/base/com/mysql/main
cp module.xml ${KEYCLOAK_PATH}/modules/system/layers/base/com/mysql/main
cp mysql-connector-java-8.0.21.jar ${KEYCLOAK_PATH}/modules/system/layers/base/com/mysql/main
cp jgroups-module.xml ${KEYCLOAK_PATH}/modules/system/layers/base/org/jgroups/main/module.xml
```

Add the local admin user:

```shell
cd <path to>/keycloak-11.0.3/bin

# User (after `-u`) should match what's in the Django settings:
# `boss.settings.keycloak.KEYCLOAK_ADMIN_USER`
# Password (after `-p`) should match what's in the Django settings:
# `boss.settings.keycloak.KEYCLOAK_ADMIN_PASSWORD`
./add-user-keycloak.sh -r master -u bossadmin -p bossadmin
```

Build Keycloak Docker container:

```shell
cd <path to>/boss-manage/local-testing-support/keycloak-docker/keycloak-11.0.0
docker build -t keycloak-11.0.x .
```

Update `docker-compose.yml` with the path to your Keycloak folder.  See the
lines under `volumes:`.  This config file lives in the same folder:
`<path to>/boss-manage/local-testing-support/keycloak-docker/keycloak-11.0.0`

```yaml
version: "3"
services:
  keycloak:
    image: keycloak-11.0.x:latest
    ports:
      - '8080:8080'
      - '9990:9990'
    volumes:
      # Set this to where you unzipped KeyCloak.  Update the path on the LEFT
      # side of the colon.  The right side is the path in the Docker container
      # and should not be changed.
      - /Users/giontc1/Downloads/keycloak-11.0.3:/srv/keycloak
    networks:
      - default

networks:
  default:
```

Start Keycloak so you can add the Boss realm:

```shell
cd <path to>/boss-manage/local-testing-support/keycloak-docker/keycloak-11.0.0

# This will run Keycloak in the foreground (you'll see all output).  If you
# don't want to have it occupy your terminal, add -d to run it in the
# background.
docker compose up
```

Make a copy of 
`<path to>/boss-manage/salt_stack/salt/keycloak/files/BOSS.realm`.  This is a
JSON file.  Open the copy and look for the `users` section.  Make the `users`
section look like this (changes are replacing `xxxxx` with `bossadmin`):

```json
    "users": [{
        "username": "bossadmin",
        "credentials": [{
            "type": "password",
            "value": "bossadmin",
            "temporary": false
        }],
        "enabled": true,
        "realmRoles": [
            "superuser",
            "admin",
            "user-manager",
            "resource-manager"
        ]
    }]
```

Also change the `redirectUris` under `clients` to look like this:

```json
            "redirectUris": ["/openid/callback/login/","/openid/callback/logout/","http://localhost:8080/*"],
```

Go to http://localhost:8080/auth/admin/master/console/#/create/realm in your
browser.  Click `Select file` and select the copy you just made.  Then click
`Create`.

## Unit Tests

For unit tests, we don't need Keycloak, but we still need a MySQL database, so
we use the Boss settings file that only includes a local MySQL.

```shell
# Run all unit tests
python manage.py test --settings=boss.settings.mysql

# Run select tests using standard unittest discovery:
# https://docs.python.org/3/library/unittest.html#test-discovery
python manage.py test --settings=boss.settings.mysql \
    --testrunner=django.test.runner.DiscoverRunner \
    <standard options for discovery>
```

## Run the Development Server

Start Keycloak:

```shell
cd <path to>/boss-manage/local-testing-support/keycloak-docker/keycloak-11.0.0

# This will run Keycloak in the foreground (you'll see all output).  If you
# don't want to have it occupy your terminal, add -d to run it in the
# background.
docker compose up
```

Start Django using its built-in dev server:

```shell
python manage.py runserver --settings boss.settings.keycloak
```

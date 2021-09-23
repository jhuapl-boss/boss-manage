# keycloak-docker

This setup allows for easy running of KeyCloak 11.0.0 on a Docker host.  This
version of KeyCloak requires Java 8.  Oracle no longer allows unlicensed use of
Java and no openJDK 8 is available for MacOS.

This `Dockerfile` builds an Ubuntu container with openJDK 8 and expects the
KeyCloak distribution to be mounted in /srv/keycloak.


## Setup

Install Docker and docker-compose.

Download KeyCloak 11.0.0 and extract to a folder on your machine.

Using `boss-manage.git/salt_stack/salt/keycloak/init.sls` as a guide to copy
files from `boss-manage.git/salt_stack/salt/keycloak/files` to your KeyCloak
folder.  In the `init.sls` file, replace `/srv/keycloak` with your KeyCloak
folder.

```shell
cd <this folder>

# Build Docker image.
docker build -t keycloak-11.0.0 .
```

Edit `docker-compose.yml`.  Change this line so it points to the location of
the KeyCloak folder on your machine:


`      - /Users/giontc1/Documents/MICrONS/keycloak-11.0.0.Final:/srv/keycloak`

to

`      - /path/to/your/keycloak-11.0.0.Final:/srv/keycloak`


## Run

```shell
cd <this folder>
docker-compose up
```

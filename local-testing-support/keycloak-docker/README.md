# keycloak-docker

This folder contains Docker config files for hosting Keycloak within a Ubuntu
Docker container.

There are sub-folders for versions of Keycloak that were tested in this
fashion.  See the corresponding README.md file in the sub-folders for
directions.

Note that the Docker containers were built by disconnecting from VPN.
Otherwise, the APL proxy root certificate will have to be installed in the
container as part of the build process.  See http://proxy411/ from within the
APL network for instructions.

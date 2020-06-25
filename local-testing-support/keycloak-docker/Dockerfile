# Build a container for running the 1.9.1 version of Keycloak.
# Assume Keycloak folder mounted as a volume in /srv/keycloak.
#
# Build with:
# docker build -t keycloak-1.9.1 .

FROM ubuntu:18.04

RUN apt-get update

# KeyCloak 1.9.1 uses Java 8.
RUN apt-get install -y openjdk-8-jre

CMD ["/srv/keycloak/bin/standalone.sh", "--server-config=standalone.xml", "-b=0.0.0.0"]

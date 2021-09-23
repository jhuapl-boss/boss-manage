# Build a container for running the 11.0.0 version of Keycloak.
# Assume Keycloak folder mounted as a volume in /srv/keycloak.
#
# Build with:
# docker build -t keycloak-11.0.0 .

FROM ubuntu:20.04

RUN apt-get update

# KeyCloak 11.0.0 uses Java 8.
RUN apt-get install -y openjdk-8-jre

CMD ["/srv/keycloak/bin/standalone.sh", "--server-config=standalone.xml", "-b=0.0.0.0"]

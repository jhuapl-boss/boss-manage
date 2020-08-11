# Build Ubuntu 20.04 with Salt 3001.
#
# Build the image with: docker build -t ubuntu-20.04-salt-3001:latest .

from ubuntu:20.04

RUN apt-get update

# Install sudo because our real deployment environment requires it.
RUN apt-get install -y curl sudo

# Install APL proxy cert.
RUN mkdir -p /usr/local/share/ca-certificates/
RUN curl https://apllinuxdepot.jhuapl.edu/linux/APL-root-cert/JHUAPL-MS-Root-CA-05-21-2038-B64-text.cer > /usr/local/share/ca-certificates/JHUAPL-MS-Root-CA-05-21-2038-B64-text.crt
RUN update-ca-certificates
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

RUN curl -s -o bootstrap-salt.sh -L https://bootstrap.saltstack.com
RUN sh bootstrap-salt.sh stable 3001

CMD ["/bin/bash"]

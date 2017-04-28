# Build Python 3.6.x from source and install to /usr/local/bin.
# pip3.6.x is also installed during the build process.
#
# The JUSTVERSION variable in the install script specifies the specific Python
# version installed.
#
# Redirecting output to /dev/null is essential.  Salt hung when run
# w/o redirecting output.

python36:
  pkg.installed:
    - pkgs:
    {% if grains['os'] == 'RedHat' or grains['os'] == 'Amazon' %}
        - gcc
        - zlib-devel.x86_64
    {% elif grains['os'] == 'Ubuntu' %}
        - build-essential
        - zlib1g-dev
        - libssl-dev
        - libsqlite3-dev
    {% endif %}
        - curl

  file.managed:
    - name: /tmp/grains-os
    - contents: {{ grains['os'] }}

  cmd.run:
    - name: |
        cd /tmp
        JUSTVERSION="3.6.1"
        VERSION="Python-"$JUSTVERSION
        curl -O https://www.python.org/ftp/python/$JUSTVERSION/$VERSION.tgz
        tar -zxvf $VERSION.tgz > /dev/null
        cd $VERSION
        sudo -H ./configure > /dev/null
        sudo -H make altinstall > /dev/null
        cd /tmp
        rm -rf $VERSION
        rm $VERSION.tgz
        cd /usr/local/bin
        sudo ln -s python3.6 python3
        sudo ln -s pip3.6 pip3
        cd /usr/local/lib
        sudo ln -s python3.6 python3
    - cwd: /tmp
    - shell: /bin/bash
    - timeout: 600
    - unless: test -x /usr/local/bin/python3.6 && test -x /usr/local/bin/pip3.6

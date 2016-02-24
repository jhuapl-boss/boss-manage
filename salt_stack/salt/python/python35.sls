# Build Python 3.5.x from source and install to /usr/local/bin.
# pip3.5.x is also installed during the build process.
#
# The JUSTVERSION variable in the install script specifies the specific Python
# version installed.
#
# Redirecting output to /dev/null is essential.  Salt hung when run
# w/o redirecting output.

python35:
  pkg.installed:
    - pkgs:
        - build-essential: 11.6ubuntu6
        - zlib1g-dev: 1:1.2.8.dfsg-1ubuntu1
        - libssl-dev: 1.0.1f-1ubuntu2.16
        - libsqlite3-dev: 3.8.2-1ubuntu2.1
  cmd.run:
    - name: |
        cd /tmp
        JUSTVERSION="3.5.1"
        VERSION="Python-"$JUSTVERSION
        curl -O https://www.python.org/ftp/python/$JUSTVERSION/$VERSION.tgz
        tar -zxvf $VERSION.tgz > /dev/null
        cd $VERSION
        sudo -H ./configure > /dev/null
        sudo -H make > /dev/null
        sudo -H make altinstall > /dev/null
        cd /tmp
        rm -rf $VERSION
        rm $VERSION.tgz
        cd /usr/local/bin
        ln -s python3.5 python3
        ln -s pip3.5 pip3
        cd /usr/local/lib
        ln -s python3.5 python3
    - cwd: /tmp
    - shell: /bin/bash
    - timeout: 600
    - unless: test -x /usr/local/bin/python3.5 && test -x /usr/local/bin/pip3.5

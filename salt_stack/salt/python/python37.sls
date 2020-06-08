# Build Python 3.7.x from source and install to /usr/local/bin.
# pip3.7.x is also installed during the build process.
#
# The JUSTVERSION variable in the install script specifies the specific Python
# version installed.
#
# Redirecting output to /dev/null is essential.  Salt hung when run
# w/o redirecting output.

python37:
  pkg.installed:
    - pkgs:
        - gcc
        - openssl-devel
        - bzip2-devel
        - libffi-devel
        - curl
        
  cmd.run:
    - name: |
        cd /tmp
        JUSTVERSION="3.7.7"
        VERSION="Python-"$JUSTVERSION
        curl -O https://www.python.org/ftp/python/$JUSTVERSION/$VERSION.tgz
        tar -xf $VERSION.tgz
        cd $VERSION
        sudo -H ./configure
        sudo -H make
        sudo -H make altinstall
        cd /tmp
        rm -rf $VERSION
        rm $VERSION.tgz
        cd /usr/local/bin
        ln -s python3.7 python3
        ln -s pip3.7 pip3
        cd /usr/local/lib
        ln -s python3.7 python3
        sudo pip3 install --upgrade pip
    - cwd: /tmp
    - shell: /bin/bash
    - timeout: 3600 
    - unless: test -x /usr/local/bin/python3.7 && test -x /usr/local/bin/pip3.7

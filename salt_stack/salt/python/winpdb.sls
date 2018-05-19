include:
    - python.python35

winpdb:
  file.managed:
    - name: /tmp/rpdb2.patch
    - source: salt://python/files/rpdb2.patch
  cmd.run:
    - name: |
        cd /tmp
        VERSION="1.4.8"
        PACKAGE="winpdb-"$VERSION

        # download
        curl -O https://storage.googleapis.com/google-code-archive-downloads/v2/code.google.com/winpdb/$PACKAGE.tar.gz

        # extract
        tar -zxvf $PACKAGE.tar.gz > /dev/null
        cd $PACKAGE

        # patch
        patch < /tmp/rpdb2.patch

        # install
        python3 setup.py install
    - cwd: /tmp
    - shell: /bin/bash

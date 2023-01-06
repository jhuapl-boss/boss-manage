# Install ndingest into site-packages.
include:
    - python.python3
    - spdb

ndingest-lib:
    pip.installed:
        # DP HACK: Cannot use salt:// with pip.installed, so assume the base directory
        - name: /srv/salt/ndingest/files/ndingest.git/
        - require:
            - sls: python.python3

ndingest-firstboot:
    file.managed:
        - name: /etc/init.d/ndingest-firstboot
        - source: salt://ndingest/files/ndingest_firstboot.py
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: update-rc.d ndingest-firstboot start 88 2 3 4 5 .
        - user: root

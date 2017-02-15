# Install ndingest into site-packages.
include:
    - python.python35

ndingest-lib:
    file.recurse:
        - name: /usr/local/lib/python3/site-packages/ndingest
        - source: salt://ndingest/files/ndingest.git
        - include_empty: true
        - user: root
        - group: root
        - file_mode: 755
        - dir_mode: 755
        - require:
            - sls: python.python35

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

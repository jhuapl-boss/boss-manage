include:
    - python.python35
    - vault.client
    - aws.boto3

python-lib:
    file.recurse:
        - name: /usr/local/lib/python3/site-packages/bossutils
        - source: salt://boss-tools/files/boss-tools.git/bossutils
        - include_empty: true
        - user: root
        - group: root
        - file_mode: 755
        - dir_mode: 755

firstboot:
    file.managed:
        - name: /etc/init.d/boss-lib-firstboot
        - source: salt://boss-tools/files/firstboot.py
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: update-rc.d boss-lib-firstboot defaults 90
        - user: root

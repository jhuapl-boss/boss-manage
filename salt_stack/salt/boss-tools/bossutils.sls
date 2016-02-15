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
        - require:
            - sls: python.python35

firstboot:
    file.managed:
        - name: /etc/init.d/bossutils-firstboot
        - source: salt://boss-tools/files/firstboot.py
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: update-rc.d bossutils-firstboot defaults 10
        - user: root

logging:
    file.directory:
        - name: /var/log/boss
        - user: ubuntu
        - group: www-data
        - dir_mode: 775


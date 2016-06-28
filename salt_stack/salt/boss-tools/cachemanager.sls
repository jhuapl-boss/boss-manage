include:
    - python.python35
    - boss-tools.bossutils
    - aws.boto3

service:
    file.managed:
        - name: /etc/init.d/preftchd
        - source: salt://boss-tools/files/boss-tools.git/cachemgr/prefetchd.py
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: update-rc.d preftchd defaults 10
        - user: root

servicedir:
    file.directory:
        - name: /var/run/prefetchd
        - user: root
        - group: root
        - dir_mode: 775


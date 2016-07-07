include:
    - python.python35
    - boss-tools.bossutils
    - aws.boto3

delayedwrite-servicedir:
    file.directory:
        - name: /var/run/boss_delayedwrited
        - user: root
        - group: root
        - dir_mode: 775

delayedwrite-service:
    file.managed:
        - name: /etc/init.d/boss_delayedwrited
        - source: salt://boss-tools/files/boss-tools.git/cachemgr/boss_delayedwrited.py
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: update-rc.d boss_delayedwrited defaults 10
        - user: root


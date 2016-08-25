include:
    - python.python35
    - boss-tools.bossutils
    - aws.boto3
    - spdb

service-cachemiss:
    file.managed:
        - name: /etc/init.d/boss-cachemissd
        - source: salt://boss-tools/files/boss-tools.git/cachemgr/boss_cachemissd.py
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: update-rc.d boss-cachemissd defaults 10
        - user: root

service-deadletter:
    file.managed:
        - name: /etc/init.d/boss-deadletterd
        - source: salt://boss-tools/files/boss-tools.git/cachemgr/boss_deadletterd.py
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: update-rc.d boss-deadletterd defaults 10
        - user: root

service-delayedwrite:
    file.managed:
        - name: /etc/init.d/boss-delayedwrited
        - source: salt://boss-tools/files/boss-tools.git/cachemgr/boss_delayedwrited.py
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: update-rc.d boss-delayedwrited defaults 10
        - user: root

service-prefetch:
    file.managed:
        - name: /etc/init.d/boss-prefetchd
        - source: salt://boss-tools/files/boss-tools.git/cachemgr/boss_prefetchd.py
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: update-rc.d boss-prefetchd defaults 10
        - user: root

#service-sqs-watcher:
#    file.managed:
#        - name: /etc/init.d/boss-sqs-watcherd
#        - source: salt://boss-tools/files/boss-tools.git/cachemgr/boss_sqs_watcherd.py
#        - user: root
#        - group: root
#        - mode: 555
#    cmd.run:
#        - name: update-rc.d boss-sqs-watcherd defaults 10
#        - user: root

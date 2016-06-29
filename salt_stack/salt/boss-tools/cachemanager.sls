include:
    - python.python35
    - boss-tools.bossutils
    - aws.boto3

prefetch-service:
    file.managed:
        - name: /etc/init.d/boss_prefetchd
        - source: salt://boss-tools/files/boss-tools.git/cachemgr/boss_prefetchd.py
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: update-rc.d boss_prefetchd defaults 10
        - user: root

prefetch-servicedir:
    file.directory:
        - name: /var/run/boss_prefetchd
        - user: root
        - group: root
        - dir_mode: 775

deadletter-service:
    file.managed:
        - name: /etc/init.d/boss_deadletterd
        - source: salt://boss-tools/files/boss-tools.git/cachemgr/boss_deadletterd.py
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: update-rc.d boss_deadletterd defaults 10
        - user: root

deadletter-servicedir:
    file.directory:
        - name: /var/run/boss_deadletterd
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

delayedwrite-servicedir:
    file.directory:
        - name: /var/run/boss_delayedwrited
        - user: root
        - group: root
        - dir_mode: 775

cachemiss-service:
   file.managed:
        - name: /etc/init.d/boss_cachemissd
        - source: salt://boss-tools/files/boss-tools.git/cachemgr/boss_cachemissd.py
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: update-rc.d boss_cachemissd defaults 10
        - user: root

cachemiss-servicedir:
    file.directory:
        - name: /var/run/boss_cachemissd
        - user: root
        - group: root
        - dir_mode: 775

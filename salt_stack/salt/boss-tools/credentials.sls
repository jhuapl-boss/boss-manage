include:
    - python.python35
    - boss-tools.bossutils

service:
    file.managed:
        - name: /etc/init.d/credentials
        - source: salt://boss-tools/files/boss-tools.git/credentials/credentials.py
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: update-rc.d credentials defaults 10
        - user: root

servicedir:
    file.directory:
        - name: /var/run/credentials
        - user: root
        - group: root
        - dir_mode: 775


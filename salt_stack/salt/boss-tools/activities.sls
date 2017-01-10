include:
    - boss-tools.bossutils
    - heaviside

activity-files:
    file.recurse:
        - name: /srv/activities
        - source: salt://boss-tools/files/boss-tools.git/activities
        - include_empty: true
        - user: root
        - group: root
        - file_mode: 755
        - dir_mode: 755
        - require:
            - sls: heaviside

manager-service:
    file.managed:
        - name: /etc/init/activity-manager.conf
        - source: salt://boss-tools/files/activity-manager
        - user: root
        - group: root
        - mode: 555
        - require:
            - file: activity-files

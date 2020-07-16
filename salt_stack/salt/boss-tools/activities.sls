include:
    - python.python3
    - python.pip3
    - boss-tools.bossutils
    - heaviside
    - python.winpdb

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

activites-lib:
    pip.installed:
        - name: pymysql
        - require:
            - sls: python.python3
            - sls: python.pip3

manager-service:
    file.managed:
        - name: /etc/init/activity-manager.conf
        - source: salt://boss-tools/files/activity-manager
        - user: root
        - group: root
        - mode: 555
        - makedirs: true
        - require:
            - file: activity-files


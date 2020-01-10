include:
    - python.python37
    - python.pip
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
        - bin_env: /usr/local/bin/pip3
        - require:
            - sls: python.python37
            - sls: python.pip

manager-service:
    file.managed:
        - name: /etc/init/activity-manager.conf
        - source: salt://boss-tools/files/activity-manager
        - user: root
        - group: root
        - mode: 555
        - require:
            - file: activity-files


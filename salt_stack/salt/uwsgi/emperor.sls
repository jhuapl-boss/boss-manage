include:
    - python.python37
    - python.pip

uwsgi:
    pip.installed:
        - name: uwsgi==2.0.12
        - bin_env: /usr/local/bin/pip3
        - require:
            - sls: python.python37
            - sls: python.pip

uwsgi-init.d:
    file.managed:
        - name: /etc/init.d/uwsgi-emperor
        - source: salt://uwsgi/files/service.sh
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: update-rc.d uwsgi-emperor defaults 20
        - user: root

/etc/uwsgi/apps-available:
    file.directory:
        - makedirs: true
        - mode: 755
        - user: root
        - group: root

/etc/uwsgi/apps-enabled:
    file.directory:
        - makedirs: true
        - mode: 755
        - user: root
        - group: root

/var/log/uwsgi:
    file.directory:
        - makedirs: true
        - mode: 755
        - user: root
        - group: root

/var/run/uwsgi:
    file.directory:
        - makedirs: true
        - mode: 755
        - user: root
        - group: root

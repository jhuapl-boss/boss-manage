include:
    - python.python35
    - python.pip
    - boss-tools.bossutils
    - uwsgi.emperor
    - nginx
    - spdb
    - boss-oidc

django-prerequirements:
    pkg.installed:
        - pkgs:
            - libmysqlclient-dev
            - libffi-dev
            - awscli

django-requirements:
    pip.installed:
        - bin_env: /usr/local/bin/pip3
        - requirements: salt://boss/files/boss.git/requirements.txt
        - exists_action: w
        - require:
            - pkg: django-prerequirements

django-files:
    file.recurse:
        - name: /srv/www
        - source: salt://boss/files/boss.git
        - include_empty: true

nginx-config:
    file.managed:
        - name: /etc/nginx/sites-available/boss
        - source: salt://boss/files/boss.git/boss_nginx.conf

nginx-enable-config:
    file.symlink:
        - name: /etc/nginx/sites-enabled/boss
        - target: /etc/nginx/sites-available/boss

uwsgi-config:
    file.managed:
        - name: /etc/uwsgi/apps-available/boss.ini
        - source: salt://boss/files/boss.git/boss_uwsgi.ini

uwsgi-enable-config:
    file.symlink:
        - name: /etc/uwsgi/apps-enabled/boss.ini
        - target: /etc/uwsgi/apps-available/boss.ini

boss-firstboot:
    file.managed:
        - name: /etc/init.d/boss-firstboot
        - source: salt://boss/files/firstboot.py
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: update-rc.d boss-firstboot start 99 2 3 4 5 .
        - user: root

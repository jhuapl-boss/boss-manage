include:
    - python.python3
    - python.pip3
    - python.python3-dev
    - boss-tools.bossutils
    - uwsgi.emperor
    - nginx
    - spdb
    - cvdb
    - git

django-prerequirements:
    pkg.installed:
        - pkgs:
            - libmysqlclient-dev
            - libffi-dev
            - awscli

django-requirements:
    pip.installed:
        - requirements: salt://boss/files/boss.git/requirements.txt
        - exists_action: w
        - require:
            - pkg: django-prerequirements

django-files:
    file.recurse:
        - name: /srv/www
        - source: salt://boss/files/boss.git
        - include_empty: true

ssl-config:
    file.managed:
        - mode: 600
        - names:
            - /etc/ssl/certs/nginx-selfsigned.crt:
                - source: salt://boss/files/nginx-selfsigned.crt
            - /etc/ssl/private/nginx-selfsigned.key:
                - source: salt://boss/files/nginx-selfsigned.key
            - /etc/nginx/dhparam.pem: 
                - source: salt://boss/files/dhparam.pem

nginx-config:
    file.managed:
        - names: 
            - /etc/nginx/sites-available/boss:
                - source: salt://boss/files/boss.git/boss_nginx.conf
            - /etc/nginx/snippets/self-signed.conf:
                - source: salt://boss/files/boss.git/self-signed.conf
            - /etc/nginx/snippets/ssl-params.conf:
                - source: salt://boss/files/boss.git/ssl-params.conf

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

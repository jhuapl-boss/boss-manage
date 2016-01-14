include:
    - python.python3
    - python.pip3
    - python.pip
    - boss-tools.bossutils
    
django-prerequirements:
    pkg.installed:
        - pkgs:
            - libmysqlclient-dev
            - nginx
            - uwsgi
            - uwsgi-plugin-python3
    
django-requirements:
    pip.installed:
        - bin_env: /usr/bin/pip3
        - requirements: salt://boss/files/boss.git/requirements.txt
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
        
nginx-disable-default:
    file.absent:
        - name: /etc/nginx/sites-enabled/default
        
uwsgi-config:
    file.managed:
        - name: /etc/uwsgi/apps-available/boss.ini
        - source: salt://boss/files/boss.git/boss_uwsgi.ini

uwsgi-enable-config:
    file.symlink:
        - name: /etc/uwsgi/apps-enabled/boss.ini
        - target: /etc/uwsgi/apps-available/boss.ini

django-firstboot:
    file.managed:
        - name: /etc/init.d/django-firstboot
        - source: salt://boss/files/firstboot.py
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: update-rc.d django-firstboot defaults 99
        - user: root
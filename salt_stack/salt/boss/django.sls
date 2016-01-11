include:
    - python.python3
    - python.pip3
    - python.pip
    
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
            - sls: python.python3
            - sls: python.pip3
            - sls: python.pip
            
django-files:
    file.recurse:
        - name: /srv/www
        - source: salt://boss/files/boss.git
        - include_empty: true
        - require:
            - sls: python.python3
            
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
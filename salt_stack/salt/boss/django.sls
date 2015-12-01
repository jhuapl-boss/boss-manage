include:
    - python3
    
django-prerequirements:
    pkg.installed:
        - name: libmysqlclient-dev
    
django-requirements:
    pip.installed:
        - bin_env: /usr/bin/pip3
        - requirements: salt://boss/files/boss.git/setup/requirements.txt
        - require:
            - pkg: django-prerequirements
            - pkg: python3-pip
            
django-files:
    file.recurse:
        - name: /srv/www
        - source: salt://boss/files/boss.git/boss
        - include_empty: true
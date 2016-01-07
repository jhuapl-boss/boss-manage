include:
    - python.python3
    - python.pip3
    - python.pip
    
django-prerequirements:
    pkg.installed:
        - name: libmysqlclient-dev
    
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
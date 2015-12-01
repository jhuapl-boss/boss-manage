include:
    - python3
    
django-requirements:
    pip.installed:
        - requirements: salt://boss/files/boss.git/boss/requirements.txt
        - require:
            - pkg: python3-pip
            
django-files:
    file.recurse:
        - name: /var/www
        - souce: salt://boss/files/boss.git/boss
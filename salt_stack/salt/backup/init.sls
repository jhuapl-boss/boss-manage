include:
    - python.python35
    - python.pip
    - mysql.client
    - boss-tools.bossutils
    - boss-tools.noconfig

rds-script:
    file.managed:
        - name: /home/ec2-user/rds.sh
        - source: salt://backup/files/rds.sh
        - user: ec2-user
        - group: ec2-user
        - mode: 555

creds-script:
    file.managed:
        - name: /home/ec2-user/creds.py
        - source: salt://backup/files/creds.py
        - user: ec2-user
        - group: ec2-user
        - mode: 555

consulate-lib:
    pip.installed:
        - name: consulate
        - bin_env: /usr/local/bin/pip3
        - require:
            - sls: python.python35
            - sls: python.pip

vault-script:
    file.managed:
        - name: /home/ec2-user/vault.py
        - source: salt://backup/files/vault.py
        - user: ec2-user
        - group: ec2-user
        - mode: 555

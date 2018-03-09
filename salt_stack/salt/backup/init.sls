rds-script:
    file.managed:
        - name: /home/ec2-user/rds.sh
        - source: salt://backup/rds.sh
        - user: ec2-user
        - group: ec2-user
        - mode: 555

creds-script:
    file.managed:
        - name: /home/ec2-user/creds.py
        - source: salt://backup/creds.py
        - user: ec2-user
        - group: ec2-user
        - mode: 555


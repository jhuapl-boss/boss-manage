include:
    - python.python35
    - vault.client
    - aws.boto3

python-lib:
    file.recurse:
        - name: /usr/local/lib/python3/site-packages/bossutils
        - source: salt://boss-tools/files/boss-tools.git/bossutils
        - include_empty: true
        - user: root
        - group: root
        - file_mode: 755
        - dir_mode: 755
        - require:
            - sls: python.python35

bossutils-firstboot:
    file.managed:
        - name: /etc/init.d/bossutils-firstboot
        - source: salt://boss-tools/files/firstboot.py
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: update-rc.d bossutils-firstboot start 10 2 3 4 5 .
        - user: root

# For VirtualBox builds, ensure this user exists.  This is the
# default user for the Amazon AMIs.
bossutils-user:
    user.present:
        - name: ubuntu

logging-normal:
    file.managed:
        - name: /var/log/boss/boss.log
        - user: ubuntu
        - group: www-data
        - makedirs: True
        - mode: 775

logging-critical:
    file.managed:
        - name: /var/log/boss/critical.log
        - user: ubuntu
        - group: www-data
        - makedirs: True
        - mode: 775

# Allow unpriviledged scripts to create
# the boss.config file
boss-config:
    file.managed:
        - name: /etc/boss/
        - makedirs: True
        - mode: 777

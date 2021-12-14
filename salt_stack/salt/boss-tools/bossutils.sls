include:
    - python.python3
    - vault.client
    - aws.boto3

python-lib:
    pip.installed:
        # DP HACK: Cannot use salt:// with pip.installed, so assume the base directory
        - name: /srv/salt/boss-tools/files/boss-tools.git/bossutils/
        - require:
            - sls: python.python3

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


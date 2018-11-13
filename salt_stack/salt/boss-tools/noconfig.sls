# Allow unpriviledged scripts to create
# the boss.config file
boss-config:
    file.managed:
        - name: /etc/boss/
        - makedirs: True
        - mode: 777


daemon:
    pkg:
        - installed
        - version: 0.6.4-1

vault-config:
    file.managed:
        - name: /etc/vault/vault.cfg
        - source: salt://vault/files/vault.cfg
        - user: root
        - group: root
        - mode: 400
        - makedirs: True
        - dir_mode: 755

vault-bin:
    file.managed:
        - name: /usr/sbin/vault
        - source: salt://vault/files/vault
        - user: root
        - group: root
        - mode: 500
        - require:
            - file: vault-config

vault-init.d:
    file.managed:
        - name: /etc/init.d/vault
        - source: salt://vault/files/service.sh
        - user: root
        - group: root
        - mode: 555
        - require:
            - pkg: daemon
            - file: vault-bin
    cmd.run:
        - name: update-rc.d vault defaults 99
        - user: root

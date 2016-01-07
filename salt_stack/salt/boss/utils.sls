include:
    - python.python3
    - vault.client

boss-utils:
    file.managed:
        - name: /usr/lib/python3/dist-packages/boss_utils/__init__.py
        - source: salt://boss/files/boss_utils.py
        - user: root
        - group: root
        - mode: 755
        - makedirs: True

boss-firstboot:
    file.managed:
        - name: /etc/init.d/boss-firstboot
        - source: salt://boss/files/firstboot.py
        - user: root
        - group: root
        - mode: 555
        - require:
            - file: boss-utils
    cmd.run:
        - name: update-rc.d boss-firstboot defaults 90
        - user: root
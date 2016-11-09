consul-daemon:
    pkg.installed:
        - name: daemon

consul-bin:
    file.managed:
        - name: /usr/sbin/consul
        - source: salt://consul/files/consul
        - user: root
        - group: root
        - mode: 500

consul-lib:
    file.managed:
        - name: /usr/lib/boss/addresses.py
        - source: salt://consul/files/addresses.py
        - user: root
        - group: root
        - mode: 555
        - makedirs: True
        - dir_mode: 755

consul-init.d:
    file.managed:
        - name: /etc/init.d/consul
        - source: salt://consul/files/service.sh
        - user: root
        - group: root
        - mode: 555
        - require:
            - file: consul-bin
            - file: consul-lib
    cmd.run:
        - name: update-rc.d consul defaults 99
        - user: root

consul-config:
    file.directory:
        - name: /etc/consul
        - user: root
        - group: root
        - dir_mode: 755

/usr/sbin/consul_cleanup:
    file.managed:
        - source: salt://consul/files/consul_cleanup.py
        - user: root
        - group: root
        - mode: 500
    cron.present:
        - identifier: CLEANUP
        - user: root
        - minute: '*/1'
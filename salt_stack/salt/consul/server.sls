daemon:
    pkg.installed: []

consul-bin:
    file.managed:
        - name: /usr/sbin/consul
        - source: salt://consul/files/consul
        - user: root
        - group: root
        - mode: 500

consul-init.d:
    file.managed:
        - name: /etc/init.d/consul
        - source: salt://consul/files/service.sh
        - user: root
        - group: root
        - mode: 555
        - require:
            - pkg: daemon
            - file: consul-bin
    cmd.run:
        - name: update-rc.d consul defaults 99
        - user: root

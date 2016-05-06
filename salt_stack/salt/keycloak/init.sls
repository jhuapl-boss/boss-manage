include:
    - sun-java
    - sun-java.env

daemon:
    pkg.installed: []

download:
    file.managed:
        - name: /tmp/keycloak.tar.gz
        - source: http://downloads.jboss.org/keycloak/1.9.1.Final/keycloak-1.9.1.Final.tar.gz
#            - salt://keycloak/files/keycloak-1.9.1.Final.tar.gz
#            - http://downloads.jboss.org/keycloak/1.9.1.Final/keycloak-1.9.1.Final.tar.gz
        - source_hash: md5=7c1b23e3a8346ba5fd42a20b5602dd61
    cmd.run:
        - name: |
            cd /srv/
            tar -x -z -f /tmp/keycloak.tar.gz -C /srv
            ln -s keycloak-1.9.1.Final keycloak
        - user: root
        - group: root

keycloak-ha-config:
    file.managed:
        - name: /srv/keycloak/standalone/configuration/standalone-ha.xml
        - source: salt://keycloak/files/standalone-ha.xml
        - mode: 644
        - require:
            - file: download

keycloak-config:
    file.managed:
        - name: /srv/keycloak/standalone/configuration/standalone.xml
        - source: salt://keycloak/files/standalone.xml
        - mode: 644
        - require:
            - file: download

keycloak-init.d:
    file.managed:
        - name: /etc/init.d/keycloak
        - source: salt://keycloak/files/service.sh
        - user: root
        - group: root
        - mode: 555
        - require:
            - pkg: daemon
    cmd.run:
        - name: update-rc.d keycloak defaults 99
        - user: root

create-java-symlink:
    file.symlink:
        - name: /usr/bin/java
        - target: /usr/lib/java/bin/java
        - force: True
        - user: root
        - group: root

mysql-config:
    file.managed:
        - name: /srv/keycloak/modules/system/layers/base/com/mysql/main/module.xml
        - source: salt://keycloak/files/module.xml
        - makedirs: True

mysql-jar:
    file.managed:
        - name: /srv/keycloak/modules/system/layers/base/com/mysql/main/mysql-connector-java-5.1.38-bin.jar
        - source: salt://keycloak/files/mysql-connector-java-5.1.38-bin.jar
        - makedirs: True

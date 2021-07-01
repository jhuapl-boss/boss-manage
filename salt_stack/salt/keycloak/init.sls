include:
    - sun-java
    - sun-java.env

daemon:
    pkg.installed: []

download:
    file.managed:
        - name: /tmp/keycloak.tar.gz
        - source: https://downloads.jboss.org/keycloak/11.0.3/keycloak-11.0.3.tar.gz
        - source_hash: sha1=87bae7fd63b49756f54e4e293fb37329f117e30d
    cmd.run:
        - name: |
            cd /srv/
            tar -x -z -f /tmp/keycloak.tar.gz -C /srv
            ln -s keycloak-11.0.3 keycloak
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
        - name: /srv/keycloak/modules/system/layers/base/com/mysql/main/mysql-connector-java-8.0.21.jar
        - source: salt://keycloak/files/mysql-connector-java-8.0.21.jar
        - makedirs: True

jgroups-config:
    file.managed:
        - name: /srv/keycloak/modules/system/layers/base/org/jgroups/main/module.xml
        - source: salt://keycloak/files/jgroups-module.xml
        - makedirs: True


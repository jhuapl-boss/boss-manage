# Ensure the local MySQL instance has the expected user and
# database for local dev and testing.

include:
  - mysql

test-mysql:
  mysql_user.present:
    - name: root
    - host: localhost
    - password: MICrONS
    - require:
      - sls: mysql

  mysql_database.present:
    - name: microns
    - connection_user: root
    - connection_pass: MICrONS
    - host: localhost
    - require:
      - sls: mysql

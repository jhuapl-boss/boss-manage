# Install and setup MySQL for testing purposes.
#
# Note that this formula should be used in conjunction with another
# formula that sets the root password using mysql_user.present.

mysql-server-5-6:
    pkg.installed:
        - name: mysql-server-5.6
    service:
        - running
        - name: mysql
        - enable: True
        - require:
            - pkg: mysql-server-5.6

login_page:
    file.managed:
        - name: /tmp/login.patch
        - source: salt://django/files/login.patch
    cmd.run:
        - name: |
            cd /usr/local/lib/python3.5/site-packages/django/contrib/admin/templates/admin/
            patch < /tmp/login.patch
        - user: root
        - group: root
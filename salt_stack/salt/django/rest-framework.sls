# This is used for our Django 1.x install.  This isn't used for Django 2.x.

include:
    - python.python35
    - python.pip

rest_framework:
    pip.installed:
        - name: djangorestframework==3.3.1
        - bin_env: /usr/local/bin/pip3
        - require:
            - sls: python.python35
            - sls: python.pip
    file.managed:
        - name: /tmp/rest_framework.patch
        - source: salt://django/files/rest_framework.patch
    cmd.run:
        - name: |
            cd /usr/local/lib/python3.5/site-packages/rest_framework/templatetags/
            patch < /tmp/rest_framework.patch
        - user: root
        - group: root

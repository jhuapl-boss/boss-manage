django:
  pip.installed:
    - name: django == 1.9.1
    - bin_env: /usr/local/bin/pip3
    - require:
      - sls: python.python35

djangorestframework:
  pip.installed:
    - name: djangorestframework == 3.3.2
    - bin_env: /usr/local/bin/pip3
    - require:
      - sls: python.python35

django-filter:
  pip.installed:
    - name: django-filter == 0.12.0
    - bin_env: /usr/local/bin/pip3
    - require:
      - sls: python.python35

libmysqlclient-dev:
  pkg.installed:
    - version: 5.5.46-0ubuntu0.14.04.2

mysqlclient:
  pip.installed:
    - name: mysqlclient == 1.3.7
    - bin_env: /usr/local/bin/pip3
    - require:
      - pkg: libmysqlclient-dev
      - sls: python.python35

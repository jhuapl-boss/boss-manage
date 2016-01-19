uwsgi:
  pip.installed:
    - name: uwsgi == 2.0.12
    - bin_env: /usr/local/bin/pip3
    - require:
      - sls: python.python35

/etc/uwsgi/apps-available:
  file.directory:
    - makedirs: true

/etc/uwsgi/apps-enabled:
  file.directory:
    - makedirs: true

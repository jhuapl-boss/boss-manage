include:
    - python.python35
    - python.pip

prereq:
    pkg.installed:
        - name: libffi-dev

oidc-lib:
    pip.installed:
        - name: django-oidc==0.1.3
        - bin_env: /usr/local/bin/pip3
        - require:
            - sls: python.python35
            - sls: python.pip
            - pkg: prereq
    file.managed:
        - name: /tmp/djangooidc.patch
        - source: salt://django/files/djangooidc.patch
    cmd.run:
        - name: |
            cd /usr/local/lib/python3.5/site-packages/djangooidc/
            patch < /tmp/djangooidc.patch
        - user: root
        - group: root
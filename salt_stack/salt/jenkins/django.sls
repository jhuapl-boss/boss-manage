# This is a Python 3.5 specific formula.
include:
    - python.python37
    - python.pip

django-jenkins:
    pip.installed:
        - name: django-jenkins==0.18.1
        - bin_env: /usr/local/bin/pip3
        - require:
            - sls: python.python37
            - sls: python.pip

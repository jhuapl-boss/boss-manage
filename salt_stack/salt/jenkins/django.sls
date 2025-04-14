# This is a Python 3.5 specific formula.
include:
    - python.python35
    - python.pip

django-jenkins:
    pip.installed:
        - pip_bin: /usr/bin/pip3
        - name: django-jenkins==0.18.1
        - require:
            - sls: python.python35
            - sls: python.pip

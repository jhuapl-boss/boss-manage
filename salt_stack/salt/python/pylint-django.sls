# This is a Python 3.5 specific formula.
include:
    - python.python35
    - python.pip
    - python.pylint

pylint-django:
    pip.installed:
        - name: pylint-django==0.7.1
        - bin_env: /usr/local/bin/pip3
        - require:
            - sls: python.python35
            - sls: python.pip
            - sls: python.pylint

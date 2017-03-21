# This is a Python 3.5 specific formula.
include:
    - python.python35
    - python.pip

virtualenvwrapper:
    pip.installed:
        - name: virtualenvwrapper
        - bin_env: /usr/local/bin/pip3
        - require:
            - sls: python.python35
            - sls: python.pip

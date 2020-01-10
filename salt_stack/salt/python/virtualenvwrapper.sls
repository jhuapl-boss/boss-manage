# This is a Python 3.5 specific formula.
include:
    - python.python37
    - python.pip

virtualenvwrapper:
    pip.installed:
        - name: virtualenvwrapper
        - bin_env: /usr/local/bin/pip3
        - require:
            - sls: python.python37
            - sls: python.pip

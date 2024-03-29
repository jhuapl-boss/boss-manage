# This is a Python 3.5 specific formula.
include:
    - python.python35
    - python.pip

pep8:
    pip.installed:
        - name: pep8==1.7.0
        - bin_env: /usr/local/bin/pip3
        - require:
            - sls: python.python35
            - sls: python.pip

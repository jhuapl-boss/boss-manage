# This is a Python 3.5 specific formula.
include:
    - python.python35
    - python.pip

pyminifier:
    pip.installed:
        - name: pyminifier==2.1
        - pip_bin: /usr/bin/pip3
        - require:
            - sls: python.python35
            - sls: python.pip

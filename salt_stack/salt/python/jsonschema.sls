include:
    - python.python35
    - python.pip

jsonschema:
    pip.installed:
        - pip_bin: /usr/bin/pip3
        - name: jsonschema==2.5.1
        - require:
            - sls: python.python35
            - sls: python.pip

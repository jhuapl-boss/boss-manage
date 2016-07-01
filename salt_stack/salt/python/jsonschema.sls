include:
    - python.python35
    - python.pip

jsonschema:
    pip.installed:
        - name: jsonschema==2.5.1
        - bin_env: /usr/local/bin/pip3
        - require:
            - sls: python.python35
            - sls: python.pip

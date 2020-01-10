include:
    - python.python37
    - python.pip

jsonschema:
    pip.installed:
        - name: jsonschema==2.5.1
        - bin_env: /usr/local/bin/pip3
        - require:
            - sls: python.python37
            - sls: python.pip

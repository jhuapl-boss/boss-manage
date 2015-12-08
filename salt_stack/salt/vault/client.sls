include:
    - python.python3
    - python.pip3
    - python.pip

vault-lib:
    pip.installed:
        - name: hvac
        - bin_env: /usr/bin/pip3
        - require:
            - sls: python.python3
            - sls: python.pip3
            - sls: python.pip
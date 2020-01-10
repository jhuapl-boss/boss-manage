include:
    - python.python37
    - python.pip

vault-lib:
    pip.installed:
        - name: hvac==0.6.3
        - bin_env: /usr/local/bin/pip3
        - require:
            - sls: python.python37
            - sls: python.pip

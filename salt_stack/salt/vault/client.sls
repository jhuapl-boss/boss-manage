include:
    - python.python35
    - python.pip

vault-lib:
    pip.installed:
        - name: hvac==0.6.3
        - bin_env: /usr/local/bin/pip3
        - require:
            - sls: python.python35
            - sls: python.pip

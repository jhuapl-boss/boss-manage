include:
    - python.python35
    - python.pip

vault-lib:
    pip.installed:
        # ToDo: fix needs to be kept in sync with spdb's hvac requirement.
        - name: hvac>=0.8.1
        - bin_env: /usr/local/bin/pip3
        - require:
            - sls: python.python35
            - sls: python.pip

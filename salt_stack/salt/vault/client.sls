include:
    - python.python3
    - python.pip3

vault-lib:
    pip.installed:
        # ToDo: fix needs to be kept in sync with spdb's hvac requirement.
        - name: hvac>=0.8.1
        #- bin_env: /usr/local/bin/pip3
        - require:
            - sls: python.python3
            - sls: python.pip3

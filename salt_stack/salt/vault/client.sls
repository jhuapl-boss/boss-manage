include:
    - python3

vault-lib:
    pip.installed:
        - name: hvac
        - bin_env: /usr/bin/pip3
        - require:
            - pkg: python3-pip
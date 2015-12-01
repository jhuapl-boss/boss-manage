include:
    - python3

vault-lib:
    pip.installed:
        - name: hvac
        - require:
            - pkg: python3-pip
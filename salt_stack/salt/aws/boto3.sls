include:
    - python.python35
    - python.pip

boto3:
    pip.installed:
        - name: boto3>=1.0,<2.0
        - bin_env: /usr/local/bin/pip3
        - require:
            - sls: python.python35
            - sls: python.pip

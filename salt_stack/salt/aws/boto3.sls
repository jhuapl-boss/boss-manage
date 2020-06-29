include:
    - python.python3
    - python.pip3

boto3:
    pip.installed:
        - name: boto3>=1.0,<2.0
        #- bin_env: /usr/local/bin/pip3
        - require:
            - sls: python.python3
            - sls: python.pip3

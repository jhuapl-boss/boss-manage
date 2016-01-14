include:
    - python.python3
    - python.pip3
    - python.pip

boto3:
    pip.installed:
        - name: boto3
        - bin_env: /usr/bin/pip3
        - require:
            - sls: python.python3
            - sls: python.pip3
            - sls: python.pip
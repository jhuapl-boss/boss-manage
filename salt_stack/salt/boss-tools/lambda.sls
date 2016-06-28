include:
    - python.python35
    - vault.client
    - aws.boto3

python-lib:
    file.recurse:
        - name: /usr/local/lib/python3/site-packages/lambda
        - source: salt://boss-tools/files/boss-tools.git/lambda
        - include_empty: true
        - user: root
        - group: root
        - file_mode: 755
        - dir_mode: 755
        - require:
            - sls: python.python35


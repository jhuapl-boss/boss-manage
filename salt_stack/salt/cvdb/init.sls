include:
    - python.python3

cvdb-lib:
    pip.installed:
        - name: /srv/salt/cvdb/files/cvdb.git/
        - require:
            - sls: python.python3

cvdb-test-requirements:
    pip.installed:
        - requirements: salt://cvdb/files/cvdb.git/requirements-test.txt
        - exists_action: w
        - require:
            - sls: python.python3
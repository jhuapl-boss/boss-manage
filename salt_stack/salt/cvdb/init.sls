include:
    - python.python3


cvdb-update-pip:
    pip.installed:
        - pip_bin: /usr/bin/pip3
        - name: pip
        - upgrade: True

cvdb-lib:
    pip.installed:
        - pip_bin: /usr/bin/pip3
        - name: /srv/salt/cvdb/files/cvdb.git/
        - require:
            - sls: python.python3

cvdb-test-requirements:
    pip.installed:
        - pip_bin: /usr/bin/pip3
        - requirements: salt://cvdb/files/cvdb.git/requirements-test.txt
        - exists_action: w
        - require:
            - sls: python.python3
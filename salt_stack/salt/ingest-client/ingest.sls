# Install ingest-client into site-packages.
include:
    - python.python35

ingest-client-lib:
    file.recurse:
        - name: /usr/local/lib/python3/site-packages/ingest
        - source: salt://ingest-client/files/ingest-client.git/ingest
        - include_empty: true
        - user: root
        - group: root
        - file_mode: 755
        - dir_mode: 755
        - require:
            - sls: python.python35

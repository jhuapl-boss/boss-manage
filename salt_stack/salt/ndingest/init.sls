# Install ndingest into site-packages.
include:
    - python.python35

ndingest-lib:
    file.recurse:
        - name: /usr/local/lib/python3/site-packages/ndingest
        - source: salt://ndingest/files/ndingest.git
        - include_empty: true
        - user: root
        - group: root
        - file_mode: 755
        - dir_mode: 755
        - require:
            - sls: python.python35

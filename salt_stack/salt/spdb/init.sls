include:
    - python.python35

spdb-prerequirements:
    pkg.installed:
        - pkgs:
            - libjpeg-dev
            - zlib1g-dev
            - libtiff5-dev
            - libfreetype6-dev
            - liblcms2-dev
            - libwebp-dev
            - libopenjpeg-dev

spdb-lib:
    pip.installed:
        - bin_env: /usr/local/bin/pip3
        - requirements: salt://spdb/files/spdb.git/requirements.txt
        - require:
            - pkg: spdb-prerequirements
    file.recurse:
        - name: /usr/local/lib/python3/site-packages/spdb
        - source: salt://spdb/files/spdb.git
        - include_empty: true
        - user: root
        - group: root
        - file_mode: 755
        - dir_mode: 755
        - require:
            - sls: python.python35
    cmd.run:
        - name: |
            cd /usr/local/lib/python3/site-packages/spdb/c_lib/c_version
            cp makefile_LINUX makefile
            make all
        - user: root
        - group: root
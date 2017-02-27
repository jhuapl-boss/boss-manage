# Install ingest-client into site-packages.
include:
    - python.python35

ingest-prerequirements:
    pkg.installed:
        - pkgs:
            # Needed for Pillow to compile (in requirements.txt)
            - libjpeg-dev
            - libopenjpeg-dev

# Install moto dependency separately.  Salt sets LC_ALL=C which breaks
# install of httpretty due to a Unicode error.  Unfortunately, can't
# override this variable in the pip.installed state using env_vars.  Salt
# probably sets LC_ALL after it sets the environment to  the contents of
# env_vars.  This will probably be fixed in a new version of Salt (newer
# than 8/2015).  See https://github.com/saltstack/salt/issues/19924 and
# https://github.com/saltstack/salt/pull/29340.
ingest-httpretty:
    cmd.run:
        - name: |
            export LC_ALL=en_US.UTF-8
            sudo /usr/local/bin/pip3 install httpretty==0.8.10

ingest-client-lib:
    pip.installed:
        - bin_env: /usr/local/bin/pip3
        - requirements: salt://ingest-client/files/ingest-client.git/requirements.txt
        - require:
            - pkg: ingest-prerequirements
            - cmd: ingest-httpretty

    file.recurse:
        - name: /usr/local/lib/python3/site-packages/ingestclient
        - source: salt://ingest-client/files/ingest-client.git/ingestclient
        - include_empty: true
        - user: root
        - group: root
        - file_mode: 755
        - dir_mode: 755
        - require:
            - sls: python.python35

include:
    - python.python3

spdb-update-pip:
    pip.installed:
        - name: pip
        - upgrade: True

spdb-prerequirements:
    pkg.installed:
        - pkgs:
            - libjpeg-dev
            - zlib1g-dev
            - libtiff5-dev
            - libfreetype6-dev
            - liblcms2-dev
            - libwebp-dev
            #- libopenjpeg-dev

# Install moto dependency separately.  Salt sets LC_ALL=C which breaks
# install of httpretty due to a Unicode error.  Unfortunately, can't
# override this variable in the pip.installed state using env_vars.  Salt
# probably sets LC_ALL after it sets the environment to  the contents of
# env_vars.  This will probably be fixed in a new version of Salt (newer
# than 8/2015).  See https://github.com/saltstack/salt/issues/19924 and
# https://github.com/saltstack/salt/pull/29340.
#httpretty:
#    cmd.run:
#        - name: |
#            export LC_ALL=en_US.UTF-8
#            sudo /usr/local/bin/pip3 install httpretty==0.8.10

# During testing with the Docker Ubuntu 20.04 image, wheel was too old to
# complete the spdb and blosc installs.
wheel-upgrade:
    pip.installed:
        - name: wheel
        - upgrade: True
        - require:
            - sls: python.python3

spdb-lib:
    pip.installed:
        # DP HACK: Cannot use salt:// with pip.installed, so assume the base directory
        - name: /srv/salt/spdb/files/spdb.git/
        - require:
            - pkg: spdb-prerequirements
            - sls: python.python3

# Need to install pyyaml separatly to avoid problems with other requirements
spdb-pyyaml:
    pip.installed:
        - name: pyyaml
        - ignore_installed: True

spdb-test-requirements:
    pip.installed:
        - requirements: salt://spdb/files/spdb.git/requirements-test.txt
        - exists_action: w
        - require:
            - sls: python.python3

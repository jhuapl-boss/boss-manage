# Setup the lambda development/build server.
# Note that this server uses Amazon Linux so its setup
# differs from our usual Ubuntu server configuration.

{% set user = 'ec2-user' %}
{% set venv_home = '/home/' + user + '/lambdaenv' %}
{% set spdb_home = venv_home + '/local/lib/python3.4/site-packages/spdb' %}
{% set bossutils_home = venv_home + '/local/lib/python3.4/site-packages/bossutils' %}
{% set lambda_home = venv_home + '/local/lib/python3.4/site-packages/lambda' %}

dev-tools:
  pkg.group_installed:
    - name: 'Development Tools'

# Install the latest Python supported by AWS Lambda.
lambda-python:
  pkg.installed:
    - pkgs: 
      - python34.x86_64
      - python34-pip.noarch
      - python34-devel.x86_64
      - python34-virtualenv.noarch

# Salt on Amazon Linux AMI uses python2.6 which doesn't have pip, so can't
# use pip.installed.
lambda-boto3:
  cmd.run:
    - name: /usr/bin/pip-3.4 install boto3
#  pip.installed:
#    - name: boto3
#    - bin_env: /usr/bin/pip-3.4

lambda-spdb-prerequirements:
  pkg.installed:
    - pkgs:
      - libjpeg-turbo-devel.x86_64
      - zlib-devel.x86_64
      - libtiff-devel.x86_64
      - freetype.x86_64
      - lcms2-devel.x86_64
      - libwebp-devel.x86_64
      - openjpeg-devel.x86_64

lambda-virtualenv:
  virtualenv.managed:
    - name: {{ venv_home }}
    - venv_bin: /usr/bin/virtualenv-3.4
    - user: {{ user }}
    - pip_upgrade: True
    - requirements: salt://spdb/files/spdb.git/requirements.txt

lambda-spdb-lib:
  file.recurse:
    - name: {{ spdb_home }}
    - source: salt://spdb/files/spdb.git
    - include_empty: true
    - user: {{ user }}
    - group: {{ user }}
    - file_mode: 755
    - dir_mode: 755
  cmd.run:
    - name: |
        cd {{ spdb_home }}/c_lib/c_version
        cp makefile_LINUX makefile
        make all
    - user: {{ user }}
    - group: {{ user }}
    - unless: test -e {{ spdb_home }}/c_lib/c_version/ndlib.so

lambda-boss-utils:
  file.recurse:
    - name: {{ bossutils_home }}
    - source: salt://boss-tools/files/boss-tools.git/bossutils
    - include_empty: true
    - user: {{ user }}
    - group: {{ user }}
    - file_mode: 755
    - dirmode: 755

lambda-lambda:
  file.recurse:
    - name: {{ lambda_home }}
    - source: salt://boss-tools/files/boss-tools.git/lambda
    - include_empty: true
    - user: {{ user }}
    - group: {{ user }}
    - file_mode: 755
    - dirmode: 755

lambda-boss-logger-config:
  # Replace the default logger config with the lambda config.
  # spdb does not specify a config file when creating BossLogger, so the
  # default config file must be replaced.
  file.copy:
    - name: {{ bossutils_home }}/logger_conf.json
    - source: {{ bossutils_home }}/lambda_logger_conf.json
    - force: true
    - user: {{ user }}
    - group: {{ user }}
    - mode: 755


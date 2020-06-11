# Setup the lambda development/build server.
# Note that this server uses Amazon Linux so its setup
# differs from our usual Ubuntu server configuration.

{% set user = 'ec2-user' %}
{% set venv_home = '/home/' + user + '/lambdaenv' %}
{% set spdb_home = venv_home + '/usr/lib/python3.7/site-packages/spdb' %}
{% set bossutils_home = venv_home + '/usr/lib/python3.7/site-packages/bossutils' %}
{% set lambda_home = venv_home + '/usr/lib/python3.7/site-packages/lambda' %}
{% set lambdautils_home = venv_home + '/usr/lib/python3.7/site-packages/lambdautils' %}

include:
    - node
    - python.python37

lib-dependencies:
    pkg.installed:
        - pkgs:
            - libjpeg-turbo-devel.x86_64
            - zlib-devel.x86_64
            - libtiff-devel.x86_64
            - freetype.x86_64
            - lcms2-devel.x86_64
            - libwebp-devel.x86_64
            - openjpeg-devel.x86_64

numpy-blosc-dependencies:
    pkg.installed:
        - pkgs:
            - atlas
            - atlas-devel
            - gcc
            - gcc-c++

install-thru-pip:
   pip.installed:
     - bin_env: /usr/local/bin/pip3
     - names:
       - boto3

build-lambda:
    file.managed:
        - name: /home/ec2-user/build_lambda.py
        - source: salt://lambda-dev/files/build_lambda.py
        - mode: 755
        - user: {{ user }}
        - group: {{ user }}

staging-dir:
    file.directory:
        - name: /home/ec2-user/staging
        - user: {{ user }}
        - group: {{ user }}
        - dir_mode: 755

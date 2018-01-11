# Setup the lambda development/build server.
# Note that this server uses Amazon Linux so its setup
# differs from our usual Ubuntu server configuration.

{% set user = 'ec2-user' %}
{% set venv_home = '/home/' + user + '/lambdaenv' %}
{% set spdb_home = venv_home + '/usr/lib/python3.6/site-packages/spdb' %}
{% set bossutils_home = venv_home + '/usr/lib/python3.6/site-packages/bossutils' %}
{% set lambda_home = venv_home + '/usr/lib/python3.6/site-packages/lambda' %}
{% set lambdautils_home = venv_home + '/usr/lib/python3.6/site-packages/lambdautils' %}

python36:
    pkg.installed:
        - pkgs:
            - python36
            - python36-pip
            - python36-virtualenv

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

make-domain:
    file.managed:
        - name: /home/ec2-user/makedomainenv
        - source: salt://lambda-dev/files/makedomainenv
        - mode: 755
        - user: {{ user }}
        - group: {{ user }}

sitezips-dir:
    file.directory:
        - name: /home/ec2-user/sitezips
        - user: {{ user }}
        - group: {{ user }}
        - dir_mode: 755

lambdazips-dir:
    file.directory:
        - name: /home/ec2-user/lambdazips
        - user: {{ user }}
        - group: {{ user }}
        - dir_mode: 755

virtualenvs-dir:
    file.directory:
        - name: /home/ec2-user/virtualenvs
        - user: {{ user }}
        - group: {{ user }}
        - dir_mode: 755

# Setup the lambda development/build server.
# Note that this server uses Amazon Linux so its setup
# differs from our usual Ubuntu server configuration.

{% set user = 'ec2-user' %}
{% set venv_home = '/home/' + user + '/lambdaenv' %}
{% set spdb_home = venv_home + '/local/lib/python3.6/site-packages/spdb' %}
{% set bossutils_home = venv_home + '/local/lib/python3.6/site-packages/bossutils' %}
{% set lambda_home = venv_home + '/local/lib/python3.6/site-packages/lambda' %}
{% set lambdautils_home = venv_home + '/local/lib/python3.6/site-packages/lambdautils' %}

include:
    - python.python36

#scipy-prerequirements:
#    pkg.installed:
#        - pkgs:
#            - libblas3
#            - liblapack3
#            - libblas-dev
#            - liblapack-dev
#            - libatlas-base-dev
#            - gfortran

#scipy-lib:
#    pip.installed:
#        - bin_env: /usr/local/bin/pip3
#        - pkgs:
#            - scipy
#        - require:
#            - pkg: spdb-prerequirements

make-base:
    file.managed:
        - name: /home/ec2-user/makebaseenv
        - source: salt://lambda-dev/files/makebaseenv
        - mode: 755

        - user: {{ user }}
        - group: {{ user }}
        - user: {{ user }}
        - group: {{ user }}

make-domain:
    file.managed:
        - name: /home/ec2-user/makedomainenv
        - source: salt://lambda-dev/files/makedomainenv
        - mode: 755
        - user: {{ user }}
        - group: {{ user }}

make-requirements:
    file.managed:
        - name: /home/ec2-user/requirements.txt
        - source: salt://boss-tools/files/boss-tools.git/lambda/requirements.txt
        - mode: 755
        - user: {{ user }}
        - group: {{ user }}


run-base:
    cmd.run:
        - name: |
            cd /home/ec2-user
            source ./makebaseenv
        - require:
            - file: make-base
        - user: {{ user }}
        - group: {{ user }}



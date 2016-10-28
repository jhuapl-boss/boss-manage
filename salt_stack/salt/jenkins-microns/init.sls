include:
    - git
    - python.python35
# Install 2.7.x pip so Salt's pip module can run.
    - python.pip
    - jenkins
    - jenkins.plugins
    - jenkins.slack
    - jenkins.jobs
# tox is probably unnecessary if we only target a single Python version.
# - python.tox
    - python.nose2-3
    - python.nose2-cov-3
    - vault.client
    - aws.boto3

## TODO: make pip installation part of the Jenkins job, instead.
intern-sdk:
    pip.installed:
        - bin_env: /usr/local/bin/pip3
        - requirements: salt://jenkins-microns/files/intern-requirements.txt

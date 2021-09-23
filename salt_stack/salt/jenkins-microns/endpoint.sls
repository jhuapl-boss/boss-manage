{% from "jenkins/map.jinja" import jenkins with context %}

include:
  - git
  - ndingest
  - ingest-client.ingest
  - boss-tools.bossutils
  - boss.django
  - mysql
  - dynamodb
  - python.coverage
  - python.pylint
  - python.pylint-django
  - python.pep8
  - python.nose2-3
  - python.nose2-cov-3
  - python.virtualenvwrapper
  - jenkins
  - jenkins.plugins
  - jenkins.slack
  - jenkins.django
  - jenkins.jobs
  - endpoint-dev.test-mysql

django_infrastructure:
  file.directory:
    - name: /var/www
    - group: www-data
    - mode: 0775

boss-config:
  file.managed:
    - name: /etc/boss/boss.config
    - source: salt://jenkins-microns/files/endpoint-boss.config
    - user: {{ jenkins.user }}
    - group: {{ jenkins.group }}
    - makedirs: True
    - mode: 0664

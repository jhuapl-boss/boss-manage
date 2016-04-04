{% from "jenkins/map.jinja" import jenkins with context %}

include:
  - git
  - boss-tools.bossutils
  - boss-tools.credentials
  - boss.django
  - django.openid-connect # install first and patch
  - mysql
  - dynamodb
  - python.coverage
  - python.pylint
  - python.pylint-django
  - python.pep8
  - jenkins
  - jenkins.plugins
  - jenkins.slack
  - jenkins.django
  - jenkins.jobs

test_db:
  mysql_user.present:
    - name: root
    - host: localhost
    - password: MICrONS
    - require:
      - sls: mysql

  mysql_database.present:
    - name: microns
    - connection_user: root
    - connection_pass: MICrONS
    - host: localhost
    - require:
      - sls: mysql

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

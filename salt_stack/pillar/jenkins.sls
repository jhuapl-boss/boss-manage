jenkins:
  lookup:
    plugins:
      installed:
        - git
        - slack
        - cobertura
    jobs:
      installed:
          example: /srv/salt/jenkins-jobs/example.xml

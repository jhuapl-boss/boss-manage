jenkins:
  lookup:
    plugins:
      installed:
        - git
        - slack
    jobs:
      installed:
          example: /srv/salt/jenkins-jobs/example.xml

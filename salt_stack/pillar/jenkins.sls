jenkins:
  lookup:
    plugins:
      installed:
        - git
        - slack
        - cobertura
    jobs:
      installed:
          boss-tools: /srv/salt/jenkins-jobs/boss-tools.xml

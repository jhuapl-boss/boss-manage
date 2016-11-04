jenkins:
  lookup:
    plugins:
      installed:
        - git
        - slack
        - cobertura
        - violations
    jobs:
      # Note that jobs can only be installed when anonymous users can run the
      # Jenkins CLI.  Once security is turned on, this is no longer the case.
      # Therefore, if Salt needs to re-run on the Jenkins server, first disable
      # security, when installing new jobs.
      installed:
          boss-tools: /srv/salt/jenkins-jobs/boss-tools.xml
          boss-manage.cloud-formation: /srv/salt/jenkins-jobs/cloud-formation.xml
          intern: /srv/salt/jenkins-jobs/intern.xml

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
          proofreader: /srv/salt/jenkins-jobs/proofreader.xml

jenkins:
  lookup:
    additional_groups: ['www-data']
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
          proofreader-init-script: /srv/salt/jenkins-jobs/proofreader-init.xml
          
          # Since proofreader triggers a build on proofreader-init-script,
          # it must be added after proofreader-init-script.
          proofreader: /srv/salt/jenkins-jobs/proofreader.xml

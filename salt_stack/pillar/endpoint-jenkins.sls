jenkins:
  lookup:
    # master_url: "{{ salt['pillar.get']('master:id', 'localhost')}}:8080"
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
          endpoint: /srv/salt/jenkins-jobs/endpoint.xml
          spdb: /srv/salt/jenkins-jobs/spdb.xml

base:
    'vault*':
        - vault.server
        - boss-tools.bossutils
        - scalyr
        - scalyr.update_host

    'endpoint*':
        - boss-tools.bossutils
        - boss-tools.credentials
        - boss.django
        - scalyr
        - scalyr.update_host
        - git

    'jenkins*':
        - jenkins-microns

    # Jenkins server for proofreader-web Django tests.
    'pr-jenkins*':
        - jenkins-microns.proofreader

    'proofreader-web*':
        - proofreader-web
        - scalyr
        - scalyr.update_host

    'workstation*':
        - python.python35
        - git
        - vault.client
        - aws.boto3

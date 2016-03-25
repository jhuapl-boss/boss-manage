base:
    'vault*':
        - vault.server
        - boss-tools.bossutils
        - scalyr
        - scalyr.update_host

    'auth*':
        - keycloak

    'endpoint*':
        - boss-tools.bossutils
        - boss-tools.credentials
        - django.openid-connect # install first and patch
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

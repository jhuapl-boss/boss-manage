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
        - django.rest-framework # install first and patch
        - boss.django
        - django.login # patch, expects django to already be installed
        - scalyr
        - scalyr.update_host
        - git

    'ep-jenkins*':
        - jenkins-microns.endpoint

    'jenkins*':
        - jenkins-microns

    # Jenkins server for proofreader-web Django tests.
    'pr-jenkins*':
        - jenkins-microns.proofreader

    'proofreader-web*':
        - django.openid-connect # install first and patch
        - django.rest-framework # install first and patch
        - proofreader-web
        - django.login # patch, expects django to already be installed
        - scalyr
        - scalyr.update_host

    'workstation*':
        - python.python35
        - git
        - vault.client
        - aws.boto3

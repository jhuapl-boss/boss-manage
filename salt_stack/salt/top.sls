base:
    'consul*':
        - consul
        - boss-tools.bossutils

    'vault*':
        - vault.server
        - boss-tools.bossutils
        - scalyr
        - scalyr.update_host

    'auth*':
        - boss-tools.bossutils
        - keycloak

    'endpoint*':
        - boss-tools.bossutils
        - ndingest
        - django.rest-framework # install first and patch
        - boss.django
        - django.login # patch, expects django to already be installed
        - scalyr
        - scalyr.update_host
        - git
        - ingest-client.ingest

    'lambda*':
        - lambda-dev

    'ep-jenkins*':
        - jenkins-microns.endpoint

    'jenkins*':
        - jenkins-microns

    # Jenkins server for proofreader-web Django tests.
    'pr-jenkins*':
        - jenkins-microns.proofreader

    'proofreader-web*':
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
        - python.pyminifier

    'cachemanager*':
        - boss-tools.bossutils
        - boss-tools.cachemanager
        - scalyr
        - scalyr.update_host
        - git

    'activities*':
        - scalyr
        - scalyr.update_host
        - boss-tools.activities

        # populate upload queue
        - ndingest
        - ingest-client.ingest

        # Resolution hierarchy
        - spdb
        - scipy

    'backup*':
        - mysql.client
        - sun-java
        - sun-java.env
        - unzip
        - users.ec2-user
        - backup
        - python.python35
        - boss-tools.bossutils

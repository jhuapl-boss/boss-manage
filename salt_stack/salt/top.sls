#
# Note Scalyr formulas are only applied if 'scalyr:log_key' set in
# pillars.


base:
    'vault*':
        - vault.server
        - boss-tools.bossutils
        - scalyr
        - scalyr.update_host
        - chrony

    'auth*':
        - boss-tools.bossutils
        - keycloak
        - chrony

    'endpoint*':
        - boss-tools.bossutils
        - ndingest
        - boss.django
        #- django.login # patch, expects django to already be installed
        - scalyr
        - scalyr.update_host
        - git
        - ingest-client.ingest
        - chrony
        - open-files.increase-open-files

    'lambda*':
        - lambda-dev

    'ep-jenkins*':
        - jenkins-microns.endpoint

    'jenkins*':
        - jenkins-microns

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
        - chrony

    'activities*':
        - scalyr
        - scalyr.update_host
        - open-files.increase-open-files
        - boss-tools.activities

        # populate upload queue
        - ndingest
        - ingest-client.ingest

        # Resolution hierarchy
        - spdb
        - scipy

        # NTP
        - chrony

    'backup*':
        - sun-java
        - sun-java.env
        - unzip
        - users.ec2-user
        - backup
        - chrony

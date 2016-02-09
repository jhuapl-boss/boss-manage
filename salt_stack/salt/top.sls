base:
    'vault':
        - vault.server
        - boss-tools.bossutils

    'endpoint*':
        - boss-tools.bossutils
        - boss.django
        - scalyr
        - scalyr.update_host

    'jenkins*':
        - jenkins-microns

    'proofreader-web*':
        - proofreader-web
        - scalyr
        - scalyr.update_host

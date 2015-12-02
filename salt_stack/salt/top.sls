base:
    'vault':
        - vault.server

    'vault-master':
        - vault.masterless
        
    'web':
        - vault.client
        - boss.django
        
    'jenkins-master*':
        - jenkins
        - jenkins.plugins
        - git
        - python.python3
        - python.pip3
        # tox is probably unnecessary if we only target a single Python version.
        # - python.tox
        - python.nose3
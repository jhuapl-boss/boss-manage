base:
    'vault':
        - vault.server

    'vault-master':
        - vault.masterless
        
    'web':
        - vault.client
        - boss.django
        
    'jenkins-master*':
        - git
        - python.python3
        - python.pip3
    - jenkins
    - jenkins.plugins
    - jenkins.slack
    - jenkins.jobs
        # tox is probably unnecessary if we only target a single Python version.
        # - python.tox
        - python.nose3
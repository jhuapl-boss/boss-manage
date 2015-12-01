base:
    'vault':
        - vault.server

    'vault-master':
        - vault.masterless
        
    'web':
        - vault.client
        - boss.django
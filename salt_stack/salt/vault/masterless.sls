include:
    - vault.server

extend:
    vault-bootstrap:
        file.managed:
            - source: salt://vault/files/bootstrap-masterless.py
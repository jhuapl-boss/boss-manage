include:
    - git
    - boss-tools.bossutils
    - proofreader-web.django
    - mysql
    - python.coverage
    - python.pylint
    - python.pylint-django
    - python.pep8
    - jenkins
    - jenkins.plugins
    - jenkins.slack
    - jenkins.django
    - jenkins.jobs
    # The proofreader has both Django and stand-alone Python code.
    - python.nose2-3
    - python.nose2-cov-3
    - python.jsonschema

test_db:
    mysql_user.present:
        - name: root
        - host: localhost
        - password: MICrONS
        - require:
            - sls: mysql

    mysql_database.present:
        - name: microns_proofreader
        - connection_user: root
        - connection_pass: MICrONS
        - host: localhost
        - require:
            - sls: mysql

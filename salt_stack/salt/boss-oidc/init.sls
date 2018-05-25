include:
    - python.python35
    - python.pip
    - git

bossoidc-prerequirements:
    pkg.installed:
        - pkgs:
            - libffi-dev

djangooidc:
    pip.installed: # pip dependencies not resolving to our version
        - bin_env: /usr/local/bin/pip3
        - editable: git+https://github.com/jhuapl-boss/django-oidc.git#egg=django-oidc
        - exists_action: w
        - require:
            - pkg: bossoidc-prerequirements

oidcauth:
    pip.installed: # pip dependencies not resolving to our version
        - bin_env: /usr/local/bin/pip3
        - editable: git+https://github.com/jhuapl-boss/drf-oidc-auth.git#egg=drf-oidc-auth
        - exists_action: w

bossoidc:
    pip.installed:
        - bin_env: /usr/local/bin/pip3
        - editable: git+https://github.com/jhuapl-boss/boss-oidc.git#egg=boss-oidc
        - exists_action: w
        - require:
            - pip: djangooidc
            - pip: oidcauth
            
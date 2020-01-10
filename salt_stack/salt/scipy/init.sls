include:
    - python.python37

scipy-prerequirements:
    pkg.installed:
        - pkgs:
            - libblas3
            - liblapack3
            - libblas-dev
            - liblapack-dev
            - libatlas-base-dev
            - gfortran

scipy-lib:
    pip.installed:
        - bin_env: /usr/local/bin/pip3
        - pkgs:
            - scipy
        - require:
            - pkg: spdb-prerequirements

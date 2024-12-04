include:
    - python.python3

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
        - pip_bin: /usr/bin/pip3
        - pkgs:
            - scipy
        - require:
            - pkg: spdb-prerequirements

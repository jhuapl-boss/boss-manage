include:
    - python.python35

scipy-prerequirements:
    pkg.installed:
        - pkgs:
            - libblas-dev
            - liblapack-dev
            - gfortran

scipy-lib:
    pip.installed:
        - bin_env: /usr/local/bin/pip3
        - pkgs: scipy
        - require:
            - pkg: spdb-prerequirements

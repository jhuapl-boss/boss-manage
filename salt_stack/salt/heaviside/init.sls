include:
    - python.python35
    - python.pip
    - git

heaviside:
    pip.installed: # pip dependencies not resolving to our version
        - bin_env: /usr/local/bin/pip3
        - editable: git+https://github.com/jhuapl-boss/heaviside.git#egg=heaviside
        - exists_action: w


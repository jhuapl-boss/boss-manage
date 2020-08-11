include:
    - python.python3
    - python.pip3
    - git

heaviside:
    pip.installed: # pip dependencies not resolving to our version
        - editable: git+https://github.com/jhuapl-boss/heaviside.git#egg=heaviside
        - exists_action: w


{% from "python/map.jinja" import python3 with context %}

include:
  - python.pip
  - python.python35

python3-nose2:
  pip.installed:
    - pip_bin: /usr/bin/pip3
    - name: {{ python3.nose2_pkg }}
    - require:
      # Currently require pip from Python 2.x for Salt's pip state.
      - sls: python.pip
      # python35 installs pip3.
      - sls: python.python35

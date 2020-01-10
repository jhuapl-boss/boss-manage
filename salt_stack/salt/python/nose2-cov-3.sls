{% from "python/map.jinja" import python3 with context %}

include:
  - python.pip
  - python.python37

python3-nose2-cov:
  pip.installed:
    - name: {{ python3.nose2_cov_pkg }}
    - bin_env: /usr/local/bin/pip3
    - require:
      # Currently require pip from Python 2.x for Salt's pip state.
      - sls: python.pip
      # python35 installs pip3.
      - sls: python.python37

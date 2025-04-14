{% from "python/map.jinja" import python2 with context %}

include:
  - python.pip

  pip.installed:
    - name: {{ python2.nose2_cov_pkg }}
    - pip_bin: /usr/bin/pip3
    - require:
      - sls: python.pip

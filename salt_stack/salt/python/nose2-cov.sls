{% from "python/map.jinja" import python2 with context %}

include:
  - python.pip

  pip.installed:
    - name: {{ python2.nose2_cov_pkg }}
    - require:
      - sls: python.pip

{% from "python/map.jinja" import python2 with context %}

include:
  - python.pip

python2-nose2:
  pip.installed:
    - name: {{ python2.nose2_pkg }}
    - require:
      - sls: python.pip

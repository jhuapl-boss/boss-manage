{% from "python/map.jinja" import python2 with context %}

python2-nose2:
  pkg.installed:
    - name: {{ python2.nose2_pkg }}

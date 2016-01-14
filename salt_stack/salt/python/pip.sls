{% from "python/map.jinja" import python2 with context %}

python2-pip:
  pkg.installed:
    - name: {{ python2.pip_pkg }}
    - version: 1.5.4-1ubuntu3

{% from "python/map.jinja" import python2 with context %}

python2-nose:
  pkg.installed:
    - name: {{ python2.nose_pkg }}

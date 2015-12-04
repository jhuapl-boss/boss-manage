{% from "python/map.jinja" import python3 with context %}

python3-nose2:
  pkg.installed:
    - name: {{ python3.nose2_pkg }}

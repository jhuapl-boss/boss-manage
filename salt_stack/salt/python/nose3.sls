{% from "python/map.jinja" import python3 with context %}

python3-nose:
  pkg.installed:
    - name: {{ python3.nose_pkg }}

{% from slspath+"/map.jinja" import chrony with context %}

chrony_removed:
  service.dead:
    - enable: False
    - name: {{ chrony.service }}
  pkg.removed:
    - name: {{ chrony.package }}
    - require:
      - service: chrony_removed

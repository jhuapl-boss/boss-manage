{% from slspath+"/map.jinja" import chrony with context %}

include:
  - chrony

chrony_config:
  file.managed:
    - name: {{ chrony.config }}
    - source: {{ chrony.config_src }}
    - template: jinja
    - defaults:
        slspath: {{ slspath|yaml_encode }}
    - user: root
    - mode: 644
    - watch_in:
      - service: chrony

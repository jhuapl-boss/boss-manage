# Check for existence of scalyr.sls at the root of a pillar folder.
{% set roots = salt['config.get']('pillar_roots:base') %}
{% set scalyr = namespace(found=false) %}
{% for path in roots if salt['file.file_exists'](path + '/scalyr.sls') %}
  {% set scalyr.found = true %}
  {% break %}
{% endfor %}

base:
{% if scalyr.found  %}
  '*':
    - scalyr
{% endif %}

  'endpoint*':
    - endpoint
    - chrony

  'cachemanager*':
    - cachemanager
    - chrony

  'activities*':
    - activities
    - chrony

  'ep-jenkins*':
    - endpoint-jenkins

  # Jenkins server for Python scripts such as those in boss-tools.
  'jenkins*':
    - jenkins

  'lambda*':
    - lambda
    - chrony

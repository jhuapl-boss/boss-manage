# Check for existence of scalyr.sls at the root of a pillar folder.
{% set roots = salt['config.get']('pillar_roots:base') %}
{% set scalyr = {'exists': false} %}
{% for path in roots if salt['file.file_exists'](path + '/scalyr.sls') %}
  {% if scalyr.update({'exists': true}) %}
    # Hack to update a variable inside a loop (not supported by Jinja version
    # used by our version of Salt).  We can update the value of a dict, though.
  {% endif %}
  {% break %}
{% endfor %}

base:
{% if scalyr.exists  %}
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

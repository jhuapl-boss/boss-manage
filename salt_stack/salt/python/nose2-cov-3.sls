{% from "python/map.jinja" import python3 with context %}

# Using pip because the nose2 coverage plugin is not available as a package
# for Ubuntu 14.
python3-nose2-cov:
  pip.installed:
    - name: {{ python3.nose2_cov_pkg }}
    - bin_env: /usr/bin/pip3
    - upgrade: True

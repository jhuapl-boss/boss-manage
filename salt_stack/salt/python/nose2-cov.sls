{% from "python/map.jinja" import python2 with context %}

# Using pip because the nose2 coverage plugin is not available as a package
# for Ubuntu 14.
python2-nose2-cov:
  pip.installed:
    - name: {{ python2.nose2_cov_pkg }}
    - upgrade: True

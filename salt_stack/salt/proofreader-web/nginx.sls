nginx:
  pkg.installed:
    - version: 1.4.6-1ubuntu3.3
  service.running:
    - require:
      - pkg: nginx

nginx:
  pkg.installed:
    - version: 1.4.6-1ubuntu3.4
  service.running:
    - require:
      - pkg: nginx
  file.absent:
    - name: /etc/nginx/sites-enabled/default

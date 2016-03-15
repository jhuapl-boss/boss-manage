nginx:
  pkg.installed: []
  service.running:
    - require:
      - pkg: nginx
  file.absent:
    - name: /etc/nginx/sites-enabled/default

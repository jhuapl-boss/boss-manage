nginx:
  pkg.installed: []
  service.running:
    - require:
      - pkg: nginx
  file.absent:
    - name: /etc/nginx/sites-enabled/default
  cmd.run: # Set the number of processes to the number of CPUs
    - name: |
        sudo sed -i.bak -e 's/worker_processes .*;/worker_processes 16;/' /etc/nginx/nginx.conf

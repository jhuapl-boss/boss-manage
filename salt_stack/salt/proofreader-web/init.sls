proofreader_client:
  file.recurse:
    - name: /tmp/proofread.git/client
    - source: salt://proofreader-web/files/proofread.git/client/
  cmd.run:
    - name: |
        npm install
        bower install --allow-root
        gulp build
        mkdir -p /srv/www/html
        cp -R /tmp/proofread.git/client/dist/* /srv/www/html
    - cwd: /tmp/proofread.git/client
    - unless: test -x /srv/www/html/index.html && test -x /srv/www/html/assets
    - require:
      - pkg: git
      - sls: proofreader-web.nodejs

proofreader_apis:
  file.recurse:
    - name: /srv/www/app/proofreader_apis
    - source: salt://proofreader-web/files/proofread.git/proofreader_apis
    - require:
      - sls: proofreader-web.django

nginx-config:
  file.managed:
    - name: /etc/nginx/sites-available/proofreader.conf
    - source: salt://proofreader-web/files/proofread.git/conf/nginx/proofreader.conf
    - require:
      - sls: proofreader-web.nginx

nginx-enable-config:
  file.symlink:
    - name: /etc/nginx/sites-enabled/proofreader.conf
    - target: /etc/nginx/sites-available/proofreader.conf
    - require:
      - sls: proofreader-web.nginx

nginx-disable-default:
  file.absent:
    - name: /etc/nginx/sites-enabled/default
    - require:
      - sls: proofreader-web.nginx

uwsgi-config:
  file.managed:
    - name: /etc/uwsgi/apps-available/proofreader_apis.ini
    - source: salt://proofreader-web/files/proofread.git/conf/uwsgi/proofreader_apis.ini
    - require:
      - sls: proofreader-web.uwsgi

uwsgi-enable-config:
  file.symlink:
    - name: /etc/uwsgi/apps-enabled/proofreader_apis.ini
    - target: /etc/uwsgi/apps-available/proofreader_apis.ini
    - require:
      - sls: proofreader-web.uwsgi

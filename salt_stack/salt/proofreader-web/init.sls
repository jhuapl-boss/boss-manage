include:
    - git
    - uwsgi.emperor
    - nginx
    - boss-tools.bossutils
    - proofreader-web.nodejs
    - proofreader-web.django

proofreader_client_build:
  file.recurse:
    - name: /tmp/proofread.git/client
    - source: salt://proofreader-web/files/proofread.git/client
  npm.bootstrap:
    - name: /tmp/proofread.git/client
    - require:
      - sls: proofreader-web.nodejs
  bower.bootstrap:
    - name: /tmp/proofread.git/client
    - require:
      - pkg: git
      - sls: proofreader-web.nodejs
  cmd.run:
    - name: gulp build
    - cwd: /tmp/proofread.git/client
    - unless: test -f /srv/www/html/index.html && test -d /srv/www/html/assets
    - require:
      - sls: proofreader-web.nodejs

proofreader_client_deploy:
  file.rename:
    - name: /srv/www/html
    - source: /tmp/proofread.git/client/dist
    - makedirs: true
    - force: true

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
      - sls: nginx

nginx-enable-config:
  file.symlink:
    - name: /etc/nginx/sites-enabled/proofreader.conf
    - target: /etc/nginx/sites-available/proofreader.conf
    - require:
      - sls: nginx

uwsgi-config:
  file.managed:
    - name: /etc/uwsgi/apps-available/proofreader_apis.ini
    - source: salt://proofreader-web/files/proofread.git/conf/uwsgi/proofreader_apis.ini
    - require:
      - sls: uwsgi.emperor

uwsgi-enable-config:
  file.symlink:
    - name: /etc/uwsgi/apps-enabled/proofreader_apis.ini
    - target: /etc/uwsgi/apps-available/proofreader_apis.ini
    - require:
      - sls: uwsgi.emperor

django-firstboot:
    file.managed:
        - name: /etc/init.d/django-firstboot
        - source: salt://proofreader-web/files/firstboot.py
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: update-rc.d django-firstboot start 99 2 3 4 5 .
        - user: root

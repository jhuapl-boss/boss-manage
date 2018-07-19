
increase-open-files:
    file.managed:
        - name: /srv/increase_open_files.sh
        - source: salt://open-files/files/increase_open_files.sh
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: /srv/increase_open_files.sh
        - user: root

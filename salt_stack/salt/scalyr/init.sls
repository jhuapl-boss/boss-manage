{% from "scalyr/map.jinja" import scalyr with context %}
{% set use_scalyr = salt['pillar.get']('scalyr:log_key', False) != False %}

{% if use_scalyr %}
    # Install the Scalyr Agent for log aggregation.
    scalyr_pkg:
        # Manually add Scalyr to package repo.
        cmd.run:
            - name: |
                VERSION="1.2.2"
                wget -q https://www.scalyr.com/scalyr-repo/stable/latest/scalyr-repo-bootstrap_${VERSION}_all.deb
                sudo dpkg -r scalyr-repo scalyr-repo-bootstrap # Remove old repo defs.
                sudo dpkg -i scalyr-repo-bootstrap_${VERSION}_all.deb
                sudo apt-get update
                rm /tmp/scalyr-repo-bootstrap_${VERSION}_all.deb
            - cwd: /tmp
            - shell: /bin/bash
            - unless: test -x /usr/sbin/scalyr-agent-2

    scalyr:
        pkg.installed:
            - pkgs:
                - scalyr-repo
                - scalyr-agent-2

    set_scalyr_log_key:
        cmd.run:
            - name: scalyr-agent-2-config --set-key "{{ salt['pillar.get']('scalyr:log_key', '') }}"

    scalyr_running:
        service.running:
            - name: scalyr-agent-2

    {% for logs, path in scalyr.log_config_files.items() %}
    scalyr_copy_log_config_{{ logs }}:
        file.managed:
            - name: /etc/scalyr-agent-2/agent.d/{{ logs }}.json
            - source:
                - {{ path }}
    {% endfor %}
{% endif %}

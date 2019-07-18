# Update the host name in /etc/scalyr-agent-2/agent.json during first
# boot.

{% set use_scalyr = salt['pillar.get']('scalyr:log_key', False) != False %}
{% if use_scalyr %}

    scalyr_set_host_name:
        file.managed:
            - name: /etc/init.d/scalyr-firstboot
            - source: salt://scalyr/files/firstboot.py
            - user: root
            - group: root
            - mode: 555
        cmd.run:
            - name: update-rc.d scalyr-firstboot start 95 2 3 4 5 .
            - user: root

{% endif %}

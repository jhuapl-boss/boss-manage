# Update the host name in /etc/scalyr-agent-2/agent.json during first
# boot.

scalyr_set_host_name:
    file.managed:
        - name: /etc/init.d/scalyr-firstboot
        - source: salt://scalyr/files/firstboot.py
        - user: root
        - group: root
        - mode: 555
    cmd.run:
        - name: update-rc.d scalyr-firstboot defaults 95
        - user: root

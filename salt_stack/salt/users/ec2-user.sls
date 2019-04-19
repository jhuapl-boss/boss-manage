ec2-user:
    cmd.run:
        - name: |
            adduser ec2-user --disabled-password
        - shell: /bin/bash
        - onlyif: test ! -d /home/ec2-user

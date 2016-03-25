dynamodb:
  cmd.run:
    - name: |
        cd /tmp
        curl -L -S -O http://dynamodb-local.s3-website-us-west-2.amazonaws.com/dynamodb_local_latest.tar.gz
        gunzip dynamodb_local_latest.tar.gz
        mkdir -p /usr/local/bin/dynamo
        mv dynamodb_local_latest.tar /usr/local/bin/dynamo
        cd /usr/local/bin/dynamo
        tar -xf dynamodb_local_latest.tar
        rm dynamodb_local_latest.tar
    - cwd: /tmp
    - shell: /bin/bash
    - timeout: 180
    - unless: test -e /usr/local/bin/dynamo/DynamoDBLocal.jar

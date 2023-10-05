#!/bin/bash

python3 -m pip install boto3 PyYaml
# domain bucket
python3 /var/task/build_lambda.py $1 $2


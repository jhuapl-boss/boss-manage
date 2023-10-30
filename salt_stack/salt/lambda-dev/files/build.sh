#!/bin/bash

# This script runs **inside** the Docker lambda build container and builds the
# lambda(s).  It is invoked by load_lambdas_on_s3() from lib/lambdas.py.
#
# Required args:
#   $1: domain name
#   $2: S3 bucket name
#   $3: hash of zip file name

set -euo pipefail

if test "$#" -ne 3; then
    echo
    echo "ERROR: $0 - must supply domain, bucket, and hash file names"
    echo
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Trust the APL Root cert so the container can use https inside of APLNIS.
cp "${SCRIPT_DIR}/JHUAPL-MS-Root-CA-05-21-2038-B64-text.crt" /etc/pki/ca-trust/source/anchors
update-ca-trust extract

# Install packages needed by build_lambda.py.
python3 -m pip install -r "${SCRIPT_DIR}/requirements.txt"

python3 "${SCRIPT_DIR}/build_lambda.py" $1 $2 $3

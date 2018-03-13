#!/usr/bin/env python3
#
# A simple script to connect to Vault, pull out the given
# path, and return the requested key value.
# Created for use by rds.sh

import sys
from bossutils.vault import Vault

if __name__ == '__main__':
    v = Vault()
    p = sys.argv[1]
    k = sys.argv[2]
    d = v.read_dict(p)
    print(d[k])

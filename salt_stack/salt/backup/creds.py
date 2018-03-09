#!/usr/bin/env python3

import sys
from bossutils.vault import Vault

if __name__ == '__main__':
    v = Vault()
    p = sys.argv[0]
    d = v.read_dict(p)
    print("{} {} {}".format(d['user'], d['password'], d['name']))

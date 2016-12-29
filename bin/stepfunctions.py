#!/usr/bin/env python3

import sys

import alter_path
from lib.stepfunctions import compile

if __name__ == '__main__':
    file_name = sys.argv[1]

    def_ = compile(file_name, indent=3)

    print(def_)

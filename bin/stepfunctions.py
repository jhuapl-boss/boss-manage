#!/usr/bin/env python3

import sys
from pathlib import Path

import alter_path
from lib.stepfunctions import compile

if __name__ == '__main__':
    file_name = sys.argv[1]

    def_ = compile(Path(file_name), region='', account_id='', indent=3)

    print(def_)

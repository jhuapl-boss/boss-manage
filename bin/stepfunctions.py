#!/usr/bin/env python3

import sys

import alter_path
from lib.stepfunctions import StateMachine

if __name__ == '__main__':
    file_name = sys.argv[1]

    machine = StateMachine("")
    def_ = machine.build(file_name, indent=3)

    print(def_)

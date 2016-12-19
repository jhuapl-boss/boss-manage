#!/usr/bin/env python3

import sys
import json
from lexer import tokenize_file
from parser import parse

from funcparserlib.parser import NoParseError

if __name__ == '__main__':
    file_name = sys.argv[1]

    tokens = tokenize_file(file_name)
    if False:
        print('\n'.join(str(t) for t in tokens))
    else:
        try:
            machine = parse(tokens)
            print(json.dumps(machine, indent=3))
        except NoParseError as e:
            print("Syntax Error: {}".format(e))
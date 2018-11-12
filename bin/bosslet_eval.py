#!/usr/bin/env python3

import alter_path
from lib import configuration

if __name__ == "__main__":
    parser = configuration.BossParser(description = "Script creating evaluating arbitray expression about a bosslet configuration file")
    parser.add_bosslet()
    parser.add_argument('expression',
                        help = 'expression to evaluate')

    args = parser.parse_args()
    rtn = eval(args.expression, {'bosslet': args.bosslet_config})
    print(rtn)

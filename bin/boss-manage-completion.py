import os
import sys
from glob import glob

import alter_path
from lib.constants import repo_path

# Generic Utilities
def normalize(filepath):
    return os.path.splitext(os.path.basename(filepath))[0]

def filter(word, words):
    return [w for w in words if w.startswith(word)]

def display(words):
    for word in words:
        print(word)

def error(msg):
    print(msg, file=sys.stderr)

def debug(msg):
    if False:
        print(msg, file=sys.stderr)

# External data loading
def load_bosslets():
    n = lambda c: normalize(c).replace('_', '.')
    bosslets = [n(c) for c in glob(repo_path('config', '*.py'))]
    custom = [n(c) for c in glob(repo_path('config', 'custom', '*.py'))]

    bosslets.extend(custom)
    return bosslets

def load_cf_configs():
    configs = [normalize(c) for c in glob(repo_path('cloud_formation', 'configs', '*.py'))]
    configs.append('all')
    configs.remove('__init__')

    return configs

def load_scenarios():
    scenarios = [normalize(s) for s in glob(repo_path('cloud_formation', 'scenarios', '*.yml'))]

    return scenarios


# Script specific argument handling
def cloudformation(argc, args):
    actions = ['create', 'update', 'delete', 'post-init', 'pre-init', 'update-migrate', 'generate']
    optionals = {'-h': 0,
                 '--help': 0,
                 '--ami-version': 1,
                 '--scenario': 1,
                 '--disable-preview': 0}

    seen_action = False
    seen_bosslet = False
    seen_configs = []
    while len(args) > 0:
        arg = args.pop(0)
        argc -= 1

        debug("loop {}: {}".format(argc, args))

        if argc == 0: # partial argument
            if not seen_action:
                actions.extend(optionals.keys())
                return filter(arg, actions)
            elif not seen_bosslet:
                bosslets = load_bosslets()
                bosslets.extend(optionals.keys())
                return filter(arg, bosslets)
            else:
                configs = load_cf_configs()
                configs.extend(optionals.keys())
                return filter(arg, configs)

        if arg in optionals:
            argc_ = optionals[arg]

            debug("{}: {}".format(arg, argc_))

            if argc_ > 0:
                while len(args) > 0 and argc_ > 0:
                    arg_ = args.pop(0)
                    argc -= 1
                    argc_ -= 1

                    if argc == 0: # partial argument
                        if arg == '--scenario':
                            return filter(arg_, load_scenarios())
                        else:
                            return [] # no autocomplete for other optional arguments

                if argc_ > 0:
                    if arg == '--scenario':
                        return load_scenarios()
                    else:
                        return [] # no autocomplete for other optional arguments

            del optionals[arg]

        elif not seen_action:
            seen_action = True
            debug("seen_action = True")
            #if arg not in actions:
            #    error("Invalid action")
        elif not seen_bosslet:
            seen_bosslet = True
            debug("seen_bosslet = True")
            #if arg not in load_bosslets():
            #    error("Invalid bosslets")
        else:
            seen_configs.append(arg)
            #if arg not in load_cf_configs():
            #    error("Invalid config")

    debug("new {}: {}".format(argc, args))

    # Next argument
    if not seen_action:
        actions.extend(optionals.keys())
        return actions
    elif not seen_bosslet:
        bosslets = load_bosslets()
        bosslets.extend(optionals.keys())
        return bosslets
    else:
        configs = load_cf_configs()
        configs.extend(optionals.keys())
        for config in seen_configs:
            configs.remove(config)
        return configs


# Script entrypoint
if __name__ == '__main__':
    argc = int(sys.argv[1])
    command = normalize(sys.argv[2])
    args = sys.argv[3:]

    debug('')
    debug("{}: {}".format(argc, args))

    if command == 'cloudformation':
        display(cloudformation(argc, args))

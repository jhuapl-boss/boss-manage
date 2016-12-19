import json

from funcparserlib.parser import (some, a, many, skip, maybe, forward_decl)
from lexer import Token

from sfn import Machine
from sfn import PassState
from sfn import TaskState, Lambda
from sfn import WaitState
from sfn import ChoiceState, Choice
from sfn import ParallelState, Branch

def link(states, final=None):
    linked = []
    for i in range(len(states)):
        state = states[i]
        linked.append(state)

        if 'Next' in state:
            continue
        if 'End' in state:
            continue

        next_ = states[i+1] if i+1 < len(states) else final

        if type(state) == ChoiceState:
            if 'Default' not in state:
                next__ = next_ # prevent branches from using the new end state (just use End=True)
                if next__ is None:
                    # DP ???: Can a choice state also end or do we need the extra state to end on?
                    next__ = PassState(str(state) + "End", end=True)
                    linked.append(next__)
                state['Default'] = str(next__)
        else:
            if next_ is None:
                state['End'] = True
            else:
                state['Next'] = str(next_)

        if hasattr(state, 'branches'):
            for name in state.branches:
                branch = state.branches[name]
                linked.extend(link(branch, final=next_))

    return linked

def make_name(line):
    return "Line{}".format(line)

const = lambda x: lambda _: x
tokval = lambda x: x.value
tokline = lambda x: x.start[0]
toktype = lambda t: some(lambda x: x.code == t) >> tokval
op = lambda s: a(Token('OP', s)) >> tokval
op_ = lambda s: skip(op(s))
n = lambda s: a(Token('NAME', s)) >> tokval
n_ = lambda s: skip(n(s))
l = lambda s: a(Token('NAME', s)) >> tokline

end = skip(a(Token('ENDMARKER', '')))
block_s = skip(toktype('INDENT'))
block_e = skip(toktype('DEDENT'))

def debug(x):
    print(x)
    return x

def make_number(n):
    try:
        return int(n)
    except ValueError:
        return float(n)

def make_string(n):
    return n[1:-1]

def make_lambda(args):
    line, func = args
    name = make_name(line)
    lambda_ = Lambda(None, func)
    return TaskState(name, lambda_)

def make_wait(args):
    line, key, value = args
    name = make_name(line)
    kwargs = {key: value}
    return WaitState(name, **kwargs)

def make_while(args):
    line, kv, steps = args
    name = make_name(line)

    choice = Choice(kv[0], kv[1], str(steps[0]))
    choices = ChoiceState(name, [choice])
    choices.branches = {line: steps}
    steps[-1]['Next'] = name # Create the loop
    return choices

def make_if_else(args):
    line, kv, steps, elif_, else_ = args

    branches = {}
    choices = []

    branches[line] = steps
    choices.append(Choice(kv[0], kv[1], str(steps[0])))

    for line_, kv_, steps_ in elif_:
        branches[line_] = steps_
        choices.append(Choice(kv_[0], kv_[1], str(steps_[0])))

    if else_:
        line_, steps_ = else_
        branches[line_] = steps_
        default = str(steps_[0])
    else:
        default = None

    name = make_name(line)
    state = ChoiceState(name, choices, default)
    state.branches = branches
    return state

def make_parallel(args):
    line, steps, parallels = args

    branches = []

    #DP XXX: calling link in the middle of parsing. should call after all states are parsed
    #        to do so, the order of steps need to be preserved
    branches.append(Branch(link(steps), str(steps[0])))

    for line_, steps_ in parallels:
        branches.append(Branch(link(steps_), str(steps_[0])))

    name = make_name(line)
    state = ParallelState(name, branches)
    return state


def parse(seq):
    number = toktype('NUMBER') >> make_number
    string = toktype('STRING') >> make_string

    lambda_ = l('Lambda') + op_('(') + string + op_(')') >> make_lambda
    wait_types = n('seconds') | n('seconds_path') | n('timestamp') | n('timestamp_path')
    wait = l('Wait') + op_('(') + wait_types + op_('=') + number + op_(')') >> make_wait
    simple_state = lambda_ | wait

    state = forward_decl()
    block = block_s + many(state) + block_e
    comparison = string + op_('==') + number + op_(':')
    while_ = l('while') + comparison + block >> make_while
    if_else = l('if') + comparison + block + many(l('elif') + comparison + block) + maybe(l('else') + op_(':') + block) >> make_if_else
    parallel = l('parallel') + op_(':') + block + many(l('parallel') + op_(':') + block) >> debug >> make_parallel
    state.define(simple_state | while_ | if_else | parallel)

    machine = many(state) + end

    states_ = machine.parse(seq)
    states_ = link(states_)

    return Machine(comment = '',
                   states = states_,
                   start = states_[0])


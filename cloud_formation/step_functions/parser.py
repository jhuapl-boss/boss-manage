import json

from funcparserlib.parser import (some, a, many, skip, maybe, forward_decl)
from lexer import Token

from sfn import Machine
from sfn import Retry, Catch
from sfn import PassState, SuccessState, FailState
from sfn import TaskState, Lambda
from sfn import WaitState
from sfn import ChoiceState, Choice
from sfn import ParallelState, Branch

def link(states, final=None):
    linked = []
    for i in range(len(states)):
        state = states[i]
        linked.append(state)

        next_ = states[i+1] if i+1 < len(states) else final

        # The first three conditions are checking to see if the state needs
        # to be linked with the next state or if it is already linked / terminates
        if 'Next' in state:
            pass
        elif 'End' in state:
            pass
        elif type(state) in (SuccessState, FailState): #terminal states
            pass
        elif type(state) == ChoiceState:
            if 'Default' not in state:
                next__ = next_ # prevent branches from using the new end state (just use End=True)
                if next__ is None:
                    # DP ???: Can a choice state also end or do we need the extra state to end on?
                    next__ = SuccessState(str(state) + "Next")
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

def make_array(n):
    if n is None:
        return []
    else:
        return [n[0]] + n[1]

def make_pass(args):
    line = args

    name = make_name(line)
    return PassState(name)

def make_success(args):
    line = args

    name = make_name(line)
    return SuccessState(name)

def make_fail(args):
    line, error, cause = args

    name = make_name(line)
    return FailState(name, error, cause)

def make_lambda(args):
    line, func, modifiers = args
    if modifiers:
        retries, catches = modifiers
    else:
        retries, catches = None, None

    name = make_name(line)
    lambda_ = Lambda(None, func)
    state = TaskState(name, lambda_, retries=retries, catches=catches)
    if catches:
        state.branches = {}
        for catch in catches:
            state.branches.update(catch.branches)
    return state

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
    line, steps, parallels, modifiers = args
    if modifiers:
        retries, catches = modifiers
    else:
        retries, catches = None, None

    branches = []

    #DP XXX: calling link in the middle of parsing. should call after all states are parsed
    #        to do so, the order of steps need to be preserved
    branches.append(Branch(link(steps), str(steps[0])))

    for line_, steps_ in parallels:
        branches.append(Branch(link(steps_), str(steps_[0])))

    name = make_name(line)
    state = ParallelState(name, branches, retries=retries, catches=catches)
    if catches:
        state.branches = {}
        for catch in catches:
            state.branches.update(catch.branches)
    return state

def make_retry(args):
    errors, interval, max_, backoff = args

    if errors == []:
        errors = ['States.ALL'] # match all errors if none is given
    return Retry(errors, interval, max_, backoff)

def make_catch(args):
    errors, steps = args
    next_ = str(steps[0])

    if errors == []:
        errors = ['States.ALL'] # match all errors if none is given
    catch = Catch(errors, next_)
    catch.branches = {next_: steps}
    return catch

def make_modifier_tuple(args):
    retry = []
    catch = []
    for modifier in args:
        if type(modifier) == Retry:
            retry.append(modifier)
        elif type(modifier) == Catch:
            catch.append(modifier)
        else:
            raise Exception("Unknown modifier type: " + type(modifier).__name__)
    if retry == []:
        retry = None
    if catch == []:
        catch = None
    return (retry, catch)


def parse(seq):
    state = forward_decl()

    number = toktype('NUMBER') >> make_number
    string = toktype('STRING') >> make_string
    array = op_('[') + maybe(string + many(op_(',') + string)) + op_(']') >> make_array
    retry = n_('retry') + (array|string) + number + number + number >> make_retry
    catch = n_('catch') + (array|string) + op_(':') + block_s + many(state) + block_e >> make_catch

    modifier = retry | catch
    modifiers = block_s + modifier + many(modifier) + block_e >> make_array >> make_modifier_tuple

    pass_ = l('Pass') + op_('(') + op_(')') >> make_pass
    success = l('Success') + op_('(') + op_(')') >> make_success
    fail = l('Fail') + op_('(') + string + op_(',') + string + op_(')') >> make_fail
    lambda_ = l('Lambda') + op_('(') + string + op_(')') + maybe(modifiers) >> debug >> make_lambda
    wait_types = n('seconds') | n('seconds_path') | n('timestamp') | n('timestamp_path')
    wait = l('Wait') + op_('(') + wait_types + op_('=') + number + op_(')') >> make_wait
    simple_state = pass_ | success | fail | lambda_ | wait

    block = block_s + many(state) + block_e
    comparison = string + op_('==') + number + op_(':')
    while_ = l('while') + comparison + block >> make_while
    if_else = (l('if') + comparison + block +
               many(l('elif') + comparison + block) +
               maybe(l('else') + op_(':') + block)) >> make_if_else
    parallel = (l('parallel') + op_(':') + block + 
                many(l('parallel') + op_(':') + block) +
                maybe(n_('error') + op_(':') + modifiers)) >> make_parallel
    state.define(simple_state | while_ | if_else | parallel)

    machine = many(state) + end

    states_ = machine.parse(seq)
    states_ = link(states_)

    return Machine(comment = '',
                   states = states_,
                   start = states_[0])


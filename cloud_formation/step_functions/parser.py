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
            for branch in state.branches:
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
    if n[:3] in ('"""', "'''"):
        return n[3:-3]
    else:
        return n[1:-1]

def make_array(n):
    if n is None:
        return []
    else:
        return [n[0]] + n[1]

def make_object(n):
    return dict(make_array(n))

def make_pass(args):
    line = args

    name = make_name(line)
    state = PassState(name)
    state.line = line
    return state

def make_success(args):
    line = args

    name = make_name(line)
    state = SuccessState(name)
    state.line = line
    return state

def make_fail(args):
    line, error, cause = args

    name = make_name(line)
    state = FailState(name, error, cause)
    state.line = line
    return state

def make_lambda(args):
    line, func = args

    name = make_name(line)
    lambda_ = Lambda(None, func)

    state = TaskState(name, lambda_)
    state.line = line
    return state

def make_wait(args):
    line, key, value = args

    name = make_name(line)
    kwargs = {key: value}

    state = WaitState(name, **kwargs)
    state.line = line
    return state

def make_while(args):
    line, kv, steps = args
    name = make_name(line)

    choice = Choice(kv[0], kv[1], str(steps[0]))
    choices = ChoiceState(name, [choice])
    choices.branches = [steps]
    steps[-1]['Next'] = name # Create the loop
    return choices

def make_if_else(args):
    line, kv, steps, elif_, else_ = args

    branches = []
    choices = []

    branches.append(steps)
    choices.append(Choice(kv[0], kv[1], str(steps[0])))

    for line_, kv_, steps_ in elif_:
        branches.append(steps_)
        choices.append(Choice(kv_[0], kv_[1], str(steps_[0])))

    if else_:
        line_, steps_ = else_
        branches.append(steps_)
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
    return ParallelState(name, branches)

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
    catch.branches = [steps]
    return catch

def make_modifiers(args):
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

def add_modifiers(args):
    state, args = args

    type_ = type(state)
    type_name = type_.__name__
    if hasattr(state, 'line'):
        target = "{} at line {}".format(type_name, state.line)
    else:
        target = "{} named {}".format(type_name, str(state))

    if args:
        comment, input_path, result_path, output_path, data, modifiers = args

        if comment:
            name, comment = comment.split('\n', 1)
            # DP TODO: cleanup comment (remove extra indents, possibly remove new lines)

            if  len(name) > 0:
                if type(state) == ChoiceState:
                    # update while loops to use the new name
                    if state.branches[0][-1]['Next'] == state.Name:
                        state.branches[0][-1]['Next'] = name
                state.Name = name

            state['Comment'] = comment

        if input_path:
            if type_ in (FailState,):
                raise Exception("{}: Cannot have 'input'".format(target))
            state['InputPath'] = input_path

        if result_path:
            if type_ in (FailState, SuccessState, WaitState):
                raise Exception("{}: Cannot have 'result'".format(target))
            state['ResultPath'] = result_path

        if output_path:
            if type_ in (FailState,):
                raise Exception("{}: Cannot have 'output'".format(target))
            state['OutputPath'] = output_path

        if data:
            if type_ != PassState:
                raise Exception("{}: Cannot have 'data'".format(target))
            state['Result'] = data

        if modifiers:
            retries, catches = modifiers
            if retries:
                if type_ in (FailState, SuccessState, PassState, WaitState):
                    raise Exception("{}: Cannot have 'retry'".format(target))
                state['Retry'] = retries
            if catches:
                if type_ in (FailState, SuccessState, PassState, WaitState):
                    raise Exception("{}: Cannot have 'catches'".format(target))
                state['Catches'] = catches
                state.branches = []
                for catch in catches:
                    state.branches.extend(catch.branches)

    return state

def json_text():
    # Taken from https://github.com/vlasovskikh/funcparserlib/blob/master/funcparserlib/tests/json.py
    # and modified slightly
    null = (n('null') | n('Null')) >> const(None)
    true = (n('true') | n('True')) >> const(True)
    false = (n('false') | n('False')) >> const(False)
    number = toktype('NUMBER') >> make_number
    string = toktype('STRING') >> make_string

    value = forward_decl()
    member = string + op_(u':') + value >> tuple
    object = (
        op_(u'{') +
        maybe(member + many(op_(u',') + member) + maybe(op_(','))) +
        op_(u'}')
        >> make_object)
    array = (
        op_(u'[') +
        maybe(value + many(op_(u',') + value) + maybe(op_(','))) +
        op_(u']')
        >> make_array)

    value.define(
        null
        | true
        | false
        | object
        | array
        | number
        | string)
    json_text = object | array

    return json_text

def parse(seq):
    state = forward_decl()

    number = toktype('NUMBER') >> make_number
    string = toktype('STRING') >> make_string
    array = op_('[') + maybe(string + many(op_(',') + string)) + op_(']') >> make_array
    retry = n_('retry') + (array|string) + number + number + number >> make_retry
    catch = n_('catch') + (array|string) + op_(':') + block_s + many(state) + block_e >> make_catch

    path = lambda t: maybe(n_(t) + op_(':') + string)
    data = n_('data') + op_(':') + block_s + json_text() + block_e
    modifier = retry | catch
    modifiers = (block_s +
                    maybe(string) +
                    path('input') +
                    path('result') +
                    path('output') +
                    maybe(data) +
                    maybe(modifier + many(modifier) >> make_array >> make_modifiers) +
                 block_e)

    pass_ = l('Pass') + op_('(') + op_(')') >> make_pass
    success = l('Success') + op_('(') + op_(')') >> make_success
    fail = l('Fail') + op_('(') + string + op_(',') + string + op_(')') >> make_fail
    lambda_ = l('Lambda') + op_('(') + string + op_(')') >> make_lambda
    task = lambda_
    wait_types = n('seconds') | n('seconds_path') | n('timestamp') | n('timestamp_path')
    wait = l('Wait') + op_('(') + wait_types + op_('=') + (number|string) + op_(')') >> make_wait
    simple_state = pass_ | success | fail | task | wait
    simple_state = simple_state + maybe(modifiers) >> add_modifiers

    block = block_s + many(state) + block_e
    comparison = string + op_('==') + number + op_(':')
    while_ = l('while') + comparison + block >> make_while
    if_else = (l('if') + comparison + block +
               many(l('elif') + comparison + block) +
               maybe(l('else') + op_(':') + block)) >> make_if_else
    parallel = (l('parallel') + op_(':') + block +
                many(l('parallel') + op_(':') + block)) >> make_parallel
    parallel_ = parallel# + maybe(n_('error') + op_(':') + modifiers) >> add_modifiers
    state.define(simple_state | while_ | if_else | parallel_)

    machine = many(state) + end

    states_ = machine.parse(seq)
    states_ = link(states_)

    return Machine(comment = '',
                   states = states_,
                   start = states_[0])


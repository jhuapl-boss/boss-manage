# AWS Step Function DSL

DP XXX: Should the DSL language and DSL compiler implementation be kept completely
        seperate? (The DSL doesn't link states together, do ARN resolution, name
        states, etc)

This document describes a domain specific language (DSL) for AWS Step Function
(SFN) state machines. The using the Python [stepfunctions] library the DSL can be
compiled down to the AWS States Language documented at [https://states-language.net/spec.html].

For more information on the Python [stepfunctions] library or its use visit the
libraries page.

Insert Copyright Statement for the DSL specification

## Table of Contents
Why
Style
Structure
Concepts
    Error Names
    Timestamps
    JSONPath
States
    Basic States
    Flow Control States

## Why
When Amazon released AWS Step Functions they provided a [https://states-language.net/spec.html](definition)
for writing state machine in. While functional, it is cumbersome to write and
maintain state machines in their JSON format. This DSL is designed to make it
easier to read, write, and maintain step function state machines.

The biggest benefit of using the DSL for writing a state machine is that when
compiled to the AWS JSON format by a library like [stepfunctions] the states can
be automatically linked together, instead of manually having to specify the next
state for each state.

The single flow control state has be translated into two of the basic flow
control operations used in programming (if/elif/else and while loop).

## Style
The DSL's style is influenced by Python code style. It is an indent based language
where the level of indent is used to specify a block of code.

EXPAND

## Structure
The SFN DSL format is an optional top level comment followed by a list of states.

### Example
    """Simple Example of the SFN DSL"""
    Lambda('HelloWorld')

Execution of the state machine is started at the first state in the file and
execution proceedes until the state at the end of the file is reached or until
a state terminates execution.

In this example there is one state. The full ARN for the Lambda will be determined
when the DSL is compiled into the AWS JSON format. The full ARN can be passed if
the desired Lambda doesn't reside in the same account or region as the connection
used to compile and create the state machine.

## Concepts
### Error Names
There is a predefined set of basic errors that can happen.
https://states-language.net/spec.html#appendix-a

### Timestamps
The SFN DSL supports comparison against timestamp values. The way a timestamp is
determined, compared to a regular string, is that it can be parsed as a timestamp
according to RFC3339. This format often looks like yyyy-mm-ddThh:mm:ssZ. If a
timestamp is not in the correct format the comparison will be performed as a
string comparison.

### JSONPath
State machines use a version of JsonPath for referencing data that is is being
processed.
https://states-language.net/spec.html#path

## States
The different types of state machine states are divided into two categories.
Basic states are those that perform a single action and, potentially, link to
another state. Flow control states are those that apply some flow control logic.

### Basic States
#### Success State
Terminal state, execution will end after this state

    Success()
        """State Name
        State Comment"""
        input: JsonPath
        output: JsonPath

#### Fail State
Terminal state, execution will end after this state
State Machine Execution will fail with the given error information
    Fail(error, cause)
        """State Name
        State Comment"""

#### Pass State
Do nothing state
Can be used to modify / inject data
    Pass()
        """State Name
        State Comment"""
        input: JsonPath
        result: JsonPath
        output: JsonPath
        data:
            Json

#### Task State
Both are considered Tasks the only difference is how the ARN will be constructed if only the name is given
    Lambda(arn | name)
    Activity(arn | name)
        """State Name
        State Comment"""
        Timeout: int
        Heartbeat: int
        input: JsonPath
        result: JsonPath
        output: JsonPath
        retry error(s) retry interval (seconds), max attempts, backoff rate
        catch error(s):
            State(s)

#### Wait State
    Wait(seconds=int)
    Wait(timestamp='yyyy-mm-ddThh:mm:ssZ')
    Wait(seconds_path=JsonPath)
    Wait(timestamp_path=JsonPath)
        """State Name
        State Comment"""
        input: JsonPath
        output: JsonPath

### Flow Control States
#### Comparison Operators
Boolean: ==, !=
Integer: ==, !=, <, >, <=, >=
Float: ==, !=, <, >, <=, >=
String: ==, !=, <, >, <=, >=
Timestamp: ==, !=, <, >, <=, >=

Comparison operators can be composed using:
* ()
* not
* and
* or

Order of precedence is the order of the list

#### If
    if JSONPath operator value:
        """State Name
        State Comment"""
        State(s) / Flow Control
    elif JSONPath operator value:
        State(s) / Flow Control
    else:
        State(s) / Flow Control
    transform:
        input: JSONPath
        result: JSONPath
        output: JSONPath

#### While Loop
    while JSONPath operator value:
        """State Name
        State Comment"""
        State(s) / Flow Control
    transform:
        input: JSONPath
        result: JSONPath
        output: JSONPath

#### Parallel
    parallel:
        """State Name
        State Comment"""
        State(s)
    parallel:
        State(s)
    transform:
        input: JSONPath
        result: JSONPath
        output: JSONPath
    error:
        Multiple retry / catch statements allowed, no ordering specified
        retry error(s) retry interval (seconds), max attempts, backoff rate
        catch error(s):
            State(s)
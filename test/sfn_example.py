#!/usr/bin/env python3

import sys
import os
import argparse
from threading import Thread

import alter_path
from lib.stepfunctions import StateMachine, Activity

sfn = """
Activity('Echo')
Wait(seconds = 30)
Activity('Echo')
"""

def run_activity(count, credentials):
    activity = Activity('Echo', credentials = credentials)

    activity.create()
    try:
        while count > 0:
            input_ = activity.task()
            if input_ is None:
                continue
            count -= 1

            print("Echo: {}".format(input_))

            activity.success(input_)
    finally:
        activity.delete()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = "Example AWS Step Function script")
    parser.add_argument("--aws-credentials", "-a",
                        metavar = "<file>",
                        default = os.environ.get("AWS_CREDENTIALS"),
                        help = "File with credentials to use when connecting to AWS (default: AWS_CREDENTIALS)")

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        print("Error: AWS credentials not provided and AWS_CREDENTIALS is not defined")
        sys.exit(1)

    credentials = args.aws_credentials

    activity = Thread(target = run_activity, args = (2, credentials))
    activity.start()

    machine = StateMachine('HelloWorld', credentials = credentials)
    if machine.arn is None:
        role = "arn:aws:iam::256215146792:role/service-role/StatesExecutionRole-us-ease-1"
        machine.create(sfn, role)
    else:
        for arn in machine.running_arns():
            macine.stop(arn, "USER", "Script automatically stops old executions")

    args = {"input": "Hello World!"}
    print("Input: {}".format(args))
    arn = machine.start(args)
    output = machine.wait(arn)
    print("Output: {}".format(output))

    machine.delete()
    activity.join()

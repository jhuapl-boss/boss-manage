from funcparserlib.parser import NoParseError

from .lexer import tokenize_source
from .parser import parse

class StateMachine(object):
    def __init__(self, name, **kwargs):
        """
        Args:
            credentials (dict|fh|filename): source to load credentials from

            Note: The following will override the values in credentials if they exist
            region (string): AWS region to connect to
            secret (string): AWS Secret Key
            access (string): AWS Access Key

            Note: The following will be derived from the AWS Session if not provided
            account_id (string): AWS Account ID
        """
        # Should statemachine name be based on the filename?
        pass

    def build(self, source, **kwargs):
        try:
            with open(source, 'r') as fh:
                tokens = tokenize_source(fh.readline)

            machine = parse(tokens)
            def_ = machine.definition(**kwargs)
            return def_
        except NoParseError as e:
            print("Syntax Error: {}".format(e))
        except:
            print("Unhandled Error: {}".format(e))

    def create(self, source):
        pass

    def _lookup_arn(self, name):
        pass

    def start(self, **kwargs):
        pass

    def stop(self):
        pass

    def status(self):
        pass


class Activity(object):
    def __init__(self, name, arn):
        pass

    def task(self):
        pass # get_activity_task

    def success(self):
        pass # send_task_success

    def failure(self):
        pass # send_task_failure

    def heartbeat(self):
        pass # send_task_heartbeat

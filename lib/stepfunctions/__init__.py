import os
import time
import json
from io import IOBase, StringIO
from collections import Mapping
from contextlib import contextmanager

from boto3.session import Session
from botocore.exceptions import ClientError
from funcparserlib.parser import NoParseError

from .lexer import tokenize_source
from .parser import parse

# DP XXX: Currently using os.path.isfile to determine if a string is a filepath or data
#         Should there also be a check to see if the string is in path format (but not a valid file)?

@contextmanager
def read(obj):
    """ Read from filepath, file object, string containing data
    """
    is_open = False
    if isinstance(obj, str):
        if os.path.isfile(obj):
            fh = open(obj, 'r')
            is_open = True
        else:
            fh = StringIO(obj)
    elif isinstance(obj, IOBase):
        fh = obj
    else:
        raise Exception("Unknown input type {}".format(type(obj).__name__))
    
    try:
        yield fh
    finally:
        if is_open:
            fh.close()

def create_session(**kwargs):
    """
    Args:
        credentials (dict|fh|filename|json string): source to load credentials from

        Note: The following will override the values in credentials if they exist
        region / aws_region (string): AWS region to connect to
        secret_key / aws_secret_key (string): AWS Secret Key
        access_key / aws_access_key (string): AWS Access Key

        Note: The following will be derived from the AWS Session if not provided
        account_id / aws_account_id (string): AWS Account ID

    Returns:
        (Boto3 Session, account_id) : Boto3 session populated with given credentials and
                                      AWS Account ID (either given or derived from session)
    """
    credentials = kwargs.get('credentials', {})
    if isinstance(credentials, Mapping):
        pass
    elif isinstance(credentials, str):
        if os.path.isfile(credentials):
            with open(credentials, 'r') as fh:
                credentials = json.load(fh)
        else:
            credentials = json.loads(credentials)
    elif isinstance(credentials, IOBase):
        credentials = json.load(credentials)
    else:
        raise Exception("Unknown credentials type: {}".format(type(credentials).__name__))

    def locate(names, locations):
        for location in locations:
            for name in names:
                if name in location:
                    return location[name]
        names = " or ".join(names)
        raise Exception("Could not find credentials value for {}".format(names))

    access = locate(('access_key', 'aws_access_key'), (kwargs, credentials))
    secret = locate(('secret_key', 'aws_secret_key'), (kwargs, credentials))
    region = locate(('region', 'aws_region'), (kwargs, credentials))

    session = Session(aws_access_key_id = access,
                      aws_secret_access_key = secret,
                      region_name = region)

    try:
        account_id = locate(('account_id', 'aws_account_id'), (kwargs, credentials))
    except:
        # From boss-manage.git/lib/aws.py:get_account_id_from_session()
        account_id = session.client('iam').list_users(MaxItems=1)["Users"][0]["Arn"].split(':')[4]

    return session, account_id

class StateMachine(object):
    def __init__(self, name, **kwargs):
        self.name = name
        self.arn = None
        self.session, self.account_id = create_session(**kwargs)
        self.client = self.session.client('stepfunctions')

        resp = self.client.list_state_machines()
        for machine in resp['stateMachines']:
            if machine['name'] == name:
                self.arn = machine['stateMachineArn']
                break

    def _translate(self, function):
        return function

    def build(self, source, **kwargs):
        try:
            with read(source) as fh:
                tokens = tokenize_source(fh.readline)

            region = self.session.region_name
            machine = parse(tokens, region, self.account_id, self._translate)
            def_ = machine.definition(**kwargs)
            return def_
        except NoParseError as e:
            print("Syntax Error: {}".format(e))
        except:
            print("Unhandled Error: {}".format(e))

    def create(self, source, role):
        if self.arn is not None:
            raise Exception("State Machine {} already exists".format(self.arn))

        # DP TODO: lookup role arn based on role name
        definition = self.build(source)

        resp = self.client.create_state_machine(name = self.name,
                                                definition = definition,
                                                roleArn = role)

        self.arn = resp['stateMachineArn']

    def delete(self, exception=False):
        if self.arn is None:
            if exception:
                raise Exception("State Machine {} doesn't exist yet".format(self.name))
        else:
            resp = self.client.delete_state_machine(stateMachineArn = self.arn)

    def start(self, input_, name=None):
        if self.arn is None:
            raise Exception("State Machine {} doesn't exist yet".format(self.name))

        if isinstance(input_, Mapping):
            input_ = json.dumps(input_)
        elif not isinstance(input_, str):
            raise Exception("Unknown input format")

        if name is None:
            name = self.name # DP TODO: add random characters

        resp = self.client.start_execution(stateMachineArn = self.arn,
                                           name = name,
                                           input = input_)

        arn = resp['executionArn']
        return arn # DP NOTE: Could store ARN in internal dict and return execution name

    def stop(self, arn, error, cause):
        resp = self.client.stop_execution(executionArn = arn,
                                          error = error,
                                          cause = cause)

    def status(self, arn):
        resp = self.client.describe_execution(executionArn = arn)
        return resp['status']

    def wait(self, arn, period=10):
        while True:
            resp = self.client.describe_execution(executionArn = arn)
            if resp['status'] != 'RUNNING':
                return resp['output']
            else:
                time.sleep(period)

    def running_arns(self):
        resp = self.client.list_executions(stateMachineArn = self.arn,
                                           statusFilter = 'RUNNING')
        return [ex['executionArn'] for ex in resp['executions']]


class Activity(object):
    def __init__(self, name, arn=None, worker=None, **kwargs):
        self.name = name
        self.arn = arn
        self.worker = worker or name # DP TODO: append random characters to the end of name
        self.token = None
        self.session, self.account_id = create_session(**kwargs)
        self.client = self.session.client('stepfunctions')

        if self.arn is None:
            resp = self.client.list_activities()
            for activity in resp['activities']:
                if activity['name'] == name:
                    self.arn = activity['activityArn']
                    break
        else:
            try:
                resp = self.client.describe_activity(activityArn = self.arn)
                if resp['name'] != name:
                    raise Exception("Name of {} is not {}".format(self.arn, self.name))
            except ClientError:
                raise Exception("ARN {} is not valid".format(self.arn))

    @property
    def exists(self):
        return self.arn is not None

    def create(self, exception = False):
        if self.exists:
            if exception:
                raise Exception("Activity {} already exists".format(self.name))
        else:
            resp = self.client.create_activity(name = self.name)
            self.arn = resp['activityArn']

    def delete(self, exception = False):
        if not self.exists:
            if exception:
                raise Exception("Activity {} doesn't exist".format(self.name))

        resp = self.client.delete_activity(activityArn = self.arn)

    def task(self):
        if self.token is not None:
            raise Exception("Currently working on a task")

        resp = self.client.get_activity_task(activityArn = self.arn,
                                             workerName = self.worker)

        if len(resp['taskToken']) == 0:
            return None
        else:
            self.token = resp['taskToken']
            return json.loads(resp['input'])

    def success(self, output):
        if self.token is None:
            raise Exception("Not currently working on a task")

        if isinstance(output, Mapping):
            output = json.dumps(output)
        elif not isinstance(output, str):
            raise Exception("Unknown output format")

        resp = self.client.send_task_success(taskToken = self.token,
                                             output = output)
        self.token = None # finished with task

    def failure(self, error, cause):
        if self.token is None:
            raise Exception("Not currently working on a task")

        resp = self.client.send_task_heartbeat(taskToken = self.token,
                                               error = error,
                                               cause = cause)
        self.token = None # finished with task

    def heartbeat(self):
        if self.token is None:
            raise Exception("Not currently working on a task")

        resp = self.client.send_task_heartbeat(taskToken = self.token)


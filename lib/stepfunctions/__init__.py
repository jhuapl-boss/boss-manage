# Copyright 2016 The Johns Hopkins University Applied Physics Laboratory
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
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
    """Context manager for reading data from multiple sources as a file object

    Args:
        obj (string|file object): Data to read / read from
                                  If obj is a file object, this is just a pass through
                                  If obj is a valid file path, this is similar to open(obj, 'r')
                                  If obj is non file path string, this creates a StringIO so
                                     the data can be read like a file object

    Returns:
        file object: File handle containing data
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

def compile(source, region=None, account_id=None, translate=None, file=sys.stderr, **kwargs):
    """Compile a source step function dsl file into the AWS state machine definition

    Args:
        source (string|file path|file object): Source of step function dsl
        region (string): AWS Region for Lambda / Activity ARNs that need to be filled in
        account_id (string): AWS Account ID for Lambda / Activity ARNs that need to be filled in
        translate (None|function): Function that translates a Lambda / Activity name before
                                   the ARN is completed
        file (file object): Where any error messages are printed (default stderr)
        kwargs (dict): Arguments to be passed to json.dumps() when creating the definition

    Returns:
        string: State machine definition
    """
    try:
        with read(source) as fh:
            tokens = tokenize_source(fh.readline)

        if translate is None:
            translate = lambda x: x

        machine = parse(tokens, region, account_id, translate)
        def_ = machine.definition(**kwargs)
        return def_
    except NoParseError as e:
        print("Syntax Error: {}".format(e), file=file)
    #except Exception as e:
    #    print("Unhandled Error: {}".format(e), file=file)

def create_session(**kwargs):
    """Create a Boto3 session from multiple different sources

    Basic file format / dictionary format:
    {
        'aws_secret_key': '',
        'aws_access_key': '',
        'aws_region': '',
        'aws_account_id': ''
    }

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
    # DP TODO: figure out how to construct Session with no arguemnts to have boto3 load keys from EC2 meta data

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
    """Class for working with and executing AWS Step Function State Machines"""

    def __init__(self, name, **kwargs):
        """
        Args:
            name (string): Name of the state machine
            kwargs (dict): Same arguments as create_session()
        """
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
        """Default implementation of a function to translate Lambda/Activity names
        before ARNs are created

        Args:
            function (string): Name of Lambda / Activity

        Returns:
            string: Name of the Lambda / Activity
        """
        return function

    def build(self, source, **kwargs):
        """Build the state machine definition from a source (file)

        Region and account id are determined from constructor arguments

        Args:
            source (string|file path|file object): Source of step function dsl
            kwargs (dict): Arguments to be passed to json.dumps() when creating the definition

        Returns:
            string: State machine definition
        """
        region = self.session.region_name
        return compile(source, region, self.account_id, self._translate, **kwargs)

    def create(self, source, role):
        """Create the state machine in AWS from the give source

        If a state machine with the given name already exists an exception is thrown

        Args:
            source (string|file path|file object): Source of step function dsl
            role (string): AWS IAM role for the state machine to execute under
        """
        if self.arn is not None:
            raise Exception("State Machine {} already exists".format(self.arn))

        # DP TODO: lookup role arn based on role name
        definition = self.build(source)

        resp = self.client.create_state_machine(name = self.name,
                                                definition = definition,
                                                roleArn = role)

        self.arn = resp['stateMachineArn']

    def delete(self, exception=False):
        """Delete the state machine from AWS

        Args:
            exception (boolean): If an excpetion should be thrown if the machine doesn't exist (default: False)
        """
        if self.arn is None:
            if exception:
                raise Exception("State Machine {} doesn't exist yet".format(self.name))
        else:
            resp = self.client.delete_state_machine(stateMachineArn = self.arn)

    def start(self, input_, name=None):
        """Start executing the state machine

        If the state machine doesn't exists an exception is thrown

        Args:
            input_ (string|dict): Json input data for the first state to process
            name (string|None): Name of the execution (default: Name of the state machine)

        Returns:
            string: ARN of the state machine execution, used to get status and output data
        """
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
        """Stop an execution of the state machine

        Args:
            arn (string): ARN of the execution to stop
            error (string): Error for the stop
            cause (string): Error cause for the stop
        """
        resp = self.client.stop_execution(executionArn = arn,
                                          error = error,
                                          cause = cause)

    def status(self, arn):
        """Get the status of an execution

        Args:
            arn (string): ARN of the execution to get the status of

        Returns:
            string: One of 'RUNNING', 'SUCCEEDED', 'FAILED', 'TIMED_OUT', 'ABORTED'
        """
        resp = self.client.describe_execution(executionArn = arn)
        return resp['status']

    def wait(self, arn, period=10):
        """Wait for an execution to finish and get the results

        Args:
            arn (string): ARN of the execution to get the status of
            period (int): Number of seconds to sleep between polls for status

        Returns:
            dict|None: Dict of Json data or None if there was an error
        """
        while True:
            resp = self.client.describe_execution(executionArn = arn)
            if resp['status'] != 'RUNNING':
                if 'output' in resp:
                    return json.loads(resp['output'])
                else:
                    return None
                    # DP TODO: figure out returning error information (and how to determine the difference between the returns)
            else:
                time.sleep(period)

    def running_arns(self):
        """Query for the ARNs of running executions

        Returns:
            list: List of strings containing the ARNs of all running executions
        """
        resp = self.client.list_executions(stateMachineArn = self.arn,
                                           statusFilter = 'RUNNING')
        return [ex['executionArn'] for ex in resp['executions']]


class Activity(object):
    """Class for work with and being an AWS Step Function Activity"""

    def __init__(self, name, arn=None, worker=None, **kwargs):
        """
        Args:
            name (string): Name of the Activity
            arn (string): ARN of the Activity (None to have it looked up)
            worker (string): Name of the worker receiving tasks (None to have one created)
            kwargs (dict): Same arguments as create_session()
        """
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
        """If the Activity exist (has an ARN in AWS)"""
        return self.arn is not None

    def create(self, exception = False):
        """Create the Activity in AWS

        Args:
            exception (boolean): If an exception should be raised if the Activity already exists (default: False)
        """
        if self.exists:
            if exception:
                raise Exception("Activity {} already exists".format(self.name))
        else:
            resp = self.client.create_activity(name = self.name)
            self.arn = resp['activityArn']

    def delete(self, exception = False):
        """Delete the Activity from AWS

        Args:
            exception (boolean): If an exception should be raised if the Activity doesn't exists (default: False)
        """
        if not self.exists:
            if exception:
                raise Exception("Activity {} doesn't exist".format(self.name))

        resp = self.client.delete_activity(activityArn = self.arn)

    def task(self):
        """Query to see if a task exists for processing.

        This methods uses a long poll, waiting up to 60 seconds before returning

        Returns:
            dict|None: Json dictionary of arguments or None if there is no task yet
        """
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
        """Marks the task successfully complete and returns the processed data

        Args:
            output (string|dict): Json response to return to the state machine
        """
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
        """Marks the task as a failure with a given reason

        Args:
            error (string): Failure error
            cause (string): Failure error cause
        """
        if self.token is None:
            raise Exception("Not currently working on a task")

        resp = self.client.send_task_heartbeat(taskToken = self.token,
                                               error = error,
                                               cause = cause)
        self.token = None # finished with task

    def heartbeat(self):
        """Sends a heartbeat for states that require heartbeats of long running Activities"""
        if self.token is None:
            raise Exception("Not currently working on a task")

        resp = self.client.send_task_heartbeat(taskToken = self.token)


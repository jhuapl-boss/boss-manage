#!/usr/bin/env python3

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

"""
Script that extracts all the messages from the Indexdeadletter queue and 
starts Index.IdWriters for the messages with operation == 'write_id_index'.
For Index.IdWriters that successfully start, the corresponding message is
deleted from the queue.
"""

import argparse
import botocore
import boto3
import json
import os
import time
from hashlib import md5

import alter_path
from lib import aws
from lib import configuration

MAX_SQS_RECEIVE = 10

class CorruptSqsResponseError(Exception):
    """
    Indicate that the response from SQS was corrupted.
    """
    pass

def check_response(msg):
    """
    Make sure message contains all the expected keys and the MD5 hash is good.

    Args:
        msg (dict): A message contained in the response returned by SQS.Client.receive_message().

    Raises:
        (CorruptSqsResponseError): If an expected key is missing from msg or the MD5 does not match.
    """
    if 'MessageId' not in msg:
        raise CorruptSqsResponseError('Message missing MessageId key')

    if 'ReceiptHandle' not in msg:
        raise CorruptSqsResponseError('Message missing ReceiptHandle key')

    if 'Body' not in msg:
        raise CorruptSqsResponseError('Message missing Body key')

    if 'MD5OfBody' not in msg:
        raise CorruptSqsResponseError('Message missing MD5OfBody key')

    if md5(msg['Body'].encode('utf-8')).hexdigest() != msg['MD5OfBody']:
        raise CorruptSqsResponseError('Message corrupt - MD5 mismatch')


def start(bosslet_config, spacing):
    """
    Main entry point of script.  Step functions are started as fast as
    possible but the first state is a delay.  The spacing argument is added to
    the total delay time, so the first step function's delay is 0 * spacing.
    The nth's step function's delay is (n-1) * spacing.

    Args:
        bosslet_config (BossConfiguration): Configuration for the target Bosslet
        spacing (int): Space start of step function's lambda task by this many seconds.
    """
    sfn_arn_prefix = 'arn:aws:states:{}:{}:stateMachine:'.format(bosslet_config.REGION,
                                                                 bosslet_config.ACCOUNT_ID)
    arn = '{}{}'.format(sfn_arn_prefix, bosslet_config.names.index_id_writer.sfn)
    queue_name = names.index_deadletter.sqs

    sqs = bosslet_config.session.client('sqs')
    resp = sqs.get_queue_url(QueueName=queue_name)
    queue_url = resp['QueueUrl']

    sfn = bosslet_config.session.client('stepfunctions')

    wait_secs = 0

    while True:
        resp = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=MAX_SQS_RECEIVE,
            WaitTimeSeconds=5,
            VisibilityTimeout=60)

        if 'Messages' not in resp or len(resp['Messages']) == 0:
            break

        for msg in resp['Messages']:
            try:
                check_response(msg)
            except CorruptSqsResponseError as ex:
                print('Skipping bad message: {}'.format(ex))
                continue

            body = json.loads(msg['Body']) 
            if 'operation' not in body:
                print('Skipping message without operation field.')
                continue

            if body['operation'] != 'write_id_index':
                print('Skipping message with operation: {}'.format(body['operation']))
                continue

            result = body.pop('result', None)
            if result is not None:
                print('Retrying Index.IdWriter that failed because: {}'.format(result['Error']))
            else:
                print('Retrying Index.IdWriter that failed because of unknown reasons.') 

            # Stagger startup of Index.IdWriters so Dynamo has more time to scale
            # if necessary.
            body['wait_secs'] = wait_secs

            try:
                sfn.start_execution(stateMachineArn=arn, input=json.dumps(body))
                wait_secs += spacing
            except botocore.exception.ClientError as ex:
                print('Failed to start Index.IdWriter: {}'.format(ex))
                continue

            try:
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=msg['ReceiptHandle'])
            except:
                print('Failed to delete message {} from queue'.format(
                    msg['MessageId']))
                continue


if __name__ == '__main__':
    parser = configuration.BossParser(description='Script for retrying Index.IdWriters that failed' + 
                                      'To supply arguments from a file, provide the filename prepended with an `@`.',
                                      fromfile_prefix_chars = '@')
    parser.add_bosslet()
    parser.add_argument('wait_secs',
                        nargs='?',
                        type=int,
                        default=10,
                        help='# seconds to space starting of step functions (default: 10)')

    args = parser.parse_args()

    start(args.bosslet_config, args.wait_secs)
    print('Done.')


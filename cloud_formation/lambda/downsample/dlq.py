# Copyright 2018 The Johns Hopkins University Applied Physics Laboratory
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

import boto3
import json

def handler(event, context):
    """Dead letter queue Lambda for downsampling process

    The downsample volume lambda uses a SNS DLQ, which invokes
    this lambda when there is an error with a lambda invocation.

    This lambda then looks at the arguments passed to the failed lambda
    to pull out the ARN/URL of a SQS queue specific to the downsample
    process that the failed lambda was launched for and puts the
    SNS event on that queue.

    The downsample activity just checks the SQS queue count to see if
    there are any error messages and will fail if there are any messages.
    """
    try:
        sqs = boto3.resource('sqs')
        args = json.loads(event['Records'][0]['Sns']['Message'])
        queue_arn = args['dlq_arn']
        try:
            queue = sqs.Queue(queue_arn)
            queue.load()
        except:
            # If the downsample activity already failed it will have already
            # deleted the queue. If the queue doesn't exists don't cause
            # this lambda to have an error message.
            print("Target queue '{}' no longer exists".format(queue_arn))
            return
        queue.send_message(MessageBody = json.dumps(event))
    except:
        print("Event: {}".format(json.dumps(event, indent=3)))
        raise

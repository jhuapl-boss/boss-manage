#!/usr/bin/env python3

# Copyright 2019 The Johns Hopkins University Applied Physics Laboratory
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

import time
import json
import itertools
from pprint import pformat

import alter_path
from lib import aws
from lib import configuration
from lib import cloudformation

def columnize(s, header=None, width=40):
    """Dump an object and make each line the given width

    The input data will run though `json.loads` in case it is a JSON object

    Args:
        s (str): Data to format
        header (optional[str]): Header to prepend to formatted results
        width (optional[int]): Max width of the resulting lines

    Returns:
        list[str]: List of formatted lines
    """

    try:
        j = json.loads(s)
    except: # Assume that the value is a string
        j = s
    s = pformat(j, width=40)
    ls = [l.ljust(width) for l in s.splitlines()]
    if header is not None:
        ls.insert(0, header.ljust(width))
        ls.insert(1, '-' * width)
    return ls

class StatusCLI(configuration.BossCLI):
    def get_parser(self, ParentParser=configuration.BossParser):
        self.parser = ParentParser(description = 'Command for displaying the current status of the bosslet')
        self.parser.add_bosslet()
        self.parser.add_argument('--diff', '-d',
                                 action='store_true',
                                 help='Display the details of the drifted resources')
        return self.parser

    def run(self, args):
        bosslet_config = args.bosslet_config
        client = bosslet_config.session.client('cloudformation')

        # Load the currently running stack information
        print("Loading stack information ...", end="", flush=True)
        existing = aws.get_existing_stacks(bosslet_config)
        print(" complete")

        # Trigger the detection of drift for the stacks
        print("Detecting drift .", end="", flush=True)
        drift_ids = { name: client.detect_stack_drift(StackName = obj['StackName'])['StackDriftDetectionId']
                      for name, obj in existing.items()
                      if obj['StackStatus'].endswith('_COMPLETE') and 
                         obj['StackStatus'] not in ('ROLLBACK_COMPLETE', ) }

        # Wait untils all of the detections have finished
        status = {}
        while len(drift_ids) > 0:
            for config, id in drift_ids.copy().items():
                resp = client.describe_stack_drift_detection_status(StackDriftDetectionId = id)
                if resp['DetectionStatus'] != 'DETECTION_IN_PROGRESS':
                    del drift_ids[config]
                    status[config] = resp
            print(".", end="", flush=True)
            time.sleep(5)
        print(" complete")

        # Sort the keys so there is a predictable order
        keys = list(existing.keys()); keys.sort()
        for config in keys:
            obj = existing[config]
            print("{} -> {}".format(config, obj['StackStatus']))
            if config in status:
                # Get the status of all of the stack's resources
                resp = aws.get_all(client.describe_stack_resource_drifts, 'StackResourceDrifts') \
                                  (StackName = obj['StackName'],
                                   StackResourceDriftStatusFilters = ['MODIFIED', 'DELETED'])
                for item in resp:
                    print("\t{} -> {}".format(item['LogicalResourceId'], item['StackResourceDriftStatus']))
                    if args.diff: # Print the details of the difference
                        for diff in item['PropertyDifferences']:
                            type = diff['DifferenceType']
                            print("\t\t{} {}".format(diff['PropertyPath'], type))
                            if type == 'REMOVE':
                                pass # Nothing to diff
                            else: # ADD | NOT_EQUAL
                                width = 40; fill = ' ' * width
                                expected = columnize(diff['ExpectedValue'], 'Expected', width)
                                actual = columnize(diff['ActualValue'], 'Actual', width)
                                for e,a in itertools.zip_longest(expected, actual, fillvalue=fill):
                                    print("\t\t{} | {}".format(e,a))
                            print()

            # DP ???: Should this be if 'ROLLBACK' in obj['StackStatus']: so that UPDATE_ROLLBACK_COMPLETE
            #         will also have the error messages printed
            elif obj['StackStatus'] == 'ROLLBACK_COMPLETE':
                config = cloudformation.CloudFormationConfiguration(config, bosslet_config)

                for reason in config.get_failed_reasons():
                    if 'cancelled' in reason:
                        continue
                    print('\t{}'.format(reason))

if __name__ == '__main__':
    cli = StatusCLI()
    cli.main()


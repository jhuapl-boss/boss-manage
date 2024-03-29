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

import argparse
import blosc
import boto3
from boto3.dynamodb.conditions import Attr
import json
from multiprocessing.pool import Pool
import os
from sys import stdout

import alter_path
from lib import aws
from lib.hosts import PROD_ACCOUNT, DEV_ACCOUNT
from lib.names import AWSNames
from lib.configuration import BossParser

from bossutils.multidimensional import XYZ, Buffer
from bossutils.multidimensional import range as xyz_range
from spdb.c_lib.ndtype import CUBOIDSIZE
from spdb.spatialdb import AWSObjectStore, Cube
from spdb.project.basicresource import BossResourceBasic

"""
Script for running the downsample process against test data.

By default, fills the first 2x2x2 cubes of the channel with random data.  If
coordinate frame extents are not provided, defaults to a large frame (see parse_args()).

The test places data directly in the S3 cuboid bucket.  Artificial ids are used
for the collection and experiment so that there is no chance of overwriting
actual data in the cuboid bucket.  To do so, letters are used for the ids of
the collection and experiment instead of integers.

Existing test data may be reused by providing the `--noupload` flag.  This
flag should also be used if you wish to test against an empty dataset.
Provide a channel id that's never been populated along with the `--noupload`
flag.


***************************************
Prerequisites
***************************************

Before running, place the parents of spdb and bossutils in the PYTHONPATH
environment variable.

AWS credentials are also required since S3 and step functions are accessed.


Sample usage:

    ./test_downsample.py -f 4096 4096 160 integration.boss 1234

This will fill a coordinate frame with x-stop: 4096, y-stop: 4096, z-stop: 160
using channel id 1234 and running in the integration stack.

To run the test again with the same data, use:

    ./test_downsample.py --noupload -f 4096 4096 160 integration.boss 1234
"""

# Format string for building the first part of step function's arn.
SFN_ARN_PREFIX_FORMAT = 'arn:aws:states:{}:{}:stateMachine:'
LAMBDA_ARN_FORMAT = 'arn:aws:lambda:{}:{}:function:{}'

def ceildiv(a, b):
    """
    Round up the result of a / b.

    From https://stackoverflow.com/questions/14822184/is-there-a-ceiling-equivalent-of-operator-in-python/17511341#17511341
    """
    return -(-a // b)

class S3Bucket(object):
    """
    Wrapper for calls to S3.
    """

    def __init__(self, session, bucket_name):
        """
        Args:
            session (boto3.Session): Open session.
            bucket_name (str):
        """
        self.bucket = bucket_name
        self.s3 = session.client('s3')

    def put(self, key, data):
        """
        Upload to bucket.

        Args:
            key (string): S3 object key.
            data (bytes|file-like object):
        """
        self.s3.put_object(Key=key, Body=data, Bucket=self.bucket)


class TestDownsample(object):

    def __init__(self, bosslet_config, chan_id, frame):
        """
        Args:
            bosslet_config (BossConfiguration): Boss Configuration of the stack when downsample should be executed
            chan_id (str): Id of channel.  Use letters to avoid collisions with real data.
            frame (list[int]): Coordinate frame x/y/z stops.
        """
        self.bosslet_config = bosslet_config
        self.chan_id = chan_id
        self.frame = frame

    def get_image_dict(self):
        """
        Generate an initial set of parameters to use to instantiate a basic 
        resource for an IMAGE dataset.

        Note that strings are not used for the ids of the collection, experiment,
        or channel.  This is to prevent accidentally overwriting real data in the
        cuboid bucket.

        Returns:
            (dict) - a dictionary of data to initialize a basic resource

        """
        data = {}
        data['boss_key'] = 'foo'
        data['lookup_key'] = 'collfake&expfake&{}'.format(self.chan_id)
        data['collection'] = {}
        data['collection']['name'] = "col1"
        data['collection']['description'] = "Test collection 1"

        data['coord_frame'] = {}
        data['coord_frame']['name'] = "coord_frame_1"
        data['coord_frame']['description'] = "Test coordinate frame"
        data['coord_frame']['x_start'] = 0
        data['coord_frame']['x_stop'] = self.frame[0]
        data['coord_frame']['y_start'] = 0
        data['coord_frame']['y_stop'] = self.frame[1]
        data['coord_frame']['z_start'] = 0
        data['coord_frame']['z_stop'] = self.frame[2]
        data['coord_frame']['x_voxel_size'] = 4
        data['coord_frame']['y_voxel_size'] = 4
        data['coord_frame']['z_voxel_size'] = 35
        data['coord_frame']['voxel_unit'] = "nanometers"

        data['experiment'] = {}
        data['experiment']['name'] = "exp1"
        data['experiment']['description'] = "Test experiment 1"
        data['experiment']['num_hierarchy_levels'] = 7
        data['experiment']['hierarchy_method'] = 'anisotropic'
        data['experiment']['num_time_samples'] = 0
        data['experiment']['time_step'] = 0
        data['experiment']['time_step_unit'] = "na"

        data['channel'] = {}
        data['channel']['name'] = "ch1"
        data['channel']['description'] = "Test channel 1"
        data['channel']['type'] = "image"
        data['channel']['datatype'] = 'uint8'
        data['channel']['base_resolution'] = 0
        data['channel']['sources'] = []
        data['channel']['related'] = []
        data['channel']['default_time_sample'] = 0
        data['channel']['downsample_status'] = "NOT_DOWNSAMPLED"

        return data

    def get_downsample_args(self):
        """
        Get arguments for starting the downsample.

        Returns:
            (dict): Arguments.
        """
        names = self.bosslet_config.names
        sfn_arn_prefix = SFN_ARN_PREFIX_FORMAT.format(self.bosslet_config.REGION,
                                                      self.bosslet_config.ACCOUNT_ID)
        start_args = {
            # resolution_hierarchy_sfn is used by the test script, but not by the
            # actual resolution hiearchy step function that the script invokes.
            'resolution_hierarchy_sfn': '{}{}'.format(sfn_arn_prefix, names.sfn.resolution_hierarchy),

            'downsample_volume_lambda': LAMBDA_ARN_FORMAT.format(self.bosslet_config.REGION,
                                                                 self.bosslet_config.ACCOUNT_ID,
                                                                 names.lambda_.downsample_volume)

            'test': True,

            'collection_id': 'collfake',
            'experiment_id': 'expfake',
            'channel_id': self.chan_id,
            'annotation_channel': False,
            'data_type': 'uint8',

            's3_index': names.s3.s3_index,
            's3_bucket': names.s3.cuboid_bucket,

            'x_start': 0,
            'y_start': 0,
            'z_start': 0,

            'x_stop': self.frame[0],
            'y_stop': self.frame[1],
            'z_stop': self.frame[2],

            'resolution': 0,
            'resolution_max': 7,
            'res_lt_max': True,

            'type': 'anisotropic',
            'iso_resolution': 3,

            'aws_region': self.bosslet_config.REGION,
        }

        return start_args

    def upload_data(self, args):
        """
        Fill the coord frame with random data.

        Args:
            args (dict): This should be the dict returned by get_downsample_args().
        """
        cuboid_size = CUBOIDSIZE[0]
        x_dim = cuboid_size[0]
        y_dim = cuboid_size[1]
        z_dim = cuboid_size[2]

        resource = BossResourceBasic()
        resource.from_dict(self.get_image_dict())
        resolution = 0
        ts = 0
        version = 0

        # DP HACK: uploading all cubes will take longer than the actual downsample
        #          just upload the first volume worth of cubes.
        #          The downsample volume lambda will only read these cubes when
        #          passed the 'test' argument.
        bucket = S3Bucket(self.bosslet_config.session, args['s3_bucket'])
        print('Uploading test data', end='', flush=True)
        for cube in xyz_range(XYZ(0,0,0), XYZ(2,2,2)):
            key = AWSObjectStore.generate_object_key(resource, resolution, ts, cube.morton)
            key += "&0" # Add the version number
            #print('morton: {}'.format(cube.morton))
            #print('key: {}'.format(key))
            #print("{} -> {} -> {}".format(cube, cube.morton, key))
            cube = Cube.create_cube(resource, [x_dim, y_dim, z_dim])
            cube.random()
            data = cube.to_blosc()
            bucket.put(key, data)
            print('.', end='', flush=True)
        print(' Done uploading.')

    def delete_data(self, args):
        lookup_prefix = '&'.join([args['collection_id'], args['experiment_id'], args['channel_id']])

        client = self.bosslet_config.session.client('s3')
        args_ = { 'Bucket': args['s3_bucket'] }
        resp = { 'KeyCount': 1 }
        count = 0
        spin = ['|', '/', '-', '\\']

        print("Deleting S3 test cubes, this may take a long time")

        while resp['KeyCount'] > 0:
            resp = client.list_objects_v2(**args_)
            args_['ContinuationToken'] = resp['NextContinuationToken']
            print("\rDeleting Cubes: Querying", end='')
            for obj in resp['Contents']:
                if lookup_prefix in obj['Key']:
                    count += 1
                    print("\rDeleting Cubes: {}".format(spin[count % 4]), end='')
                    client.delete_object(Bucket = args['s3_bucket'],
                                         Key = obj['Key'])

        print("Deleted {} cubes".format(count))


    def delete_index_keys(self, args):
        table = self.bosslet_config.session.resource('dynamodb').Table(args['s3_index'])
        lookup_prefix = '&'.join([args['collection_id'], args['experiment_id'], args['channel_id']])

        resp = {'Count': 1}
        while resp['Count'] > 0:
            resp = table.scan(FilterExpression = Attr('lookup-key').begins_with(lookup_prefix))
            print("Removing {} S3 index keys".format(resp['Count']))
            for item in resp['Items']:
                key = {
                    'object-key': item['object-key'],
                    'version-node': item['version-node'],
                }
                table.delete_item(Key = key)

def parse_args():
    """
    Parse command line or config file.

    Returns:
        (Namespace): Parsed arguments.
    """
    parser = BossParser(
        description='Script for testing downsample process. ' + 
        'To supply arguments from a file, provide the filename prepended with an `@`.',
        fromfile_prefix_chars = '@')
    parser.add_argument('--frame', '-f',
                        nargs=3,
                        type=int,
                        default=[277504, 277504, 1000],
                        help='Coordinate frame max extents (default: 277504, 277504, 1000)')
    parser.add_argument('--noupload',
                        action='store_true',
                        default=False,
                        help="Don't upload any data to the channel")
    parser.add_argument('--leave-index',
                        action = 'store_true',
                        default = False,
                        help = "Don't remove S3 Index table test keys")
    parser.add_argument('--cleanup',
                        action = 'store_true',
                        default = False,
                        help = 'Remove S3 cubes and S3 index table keys related to testing')
    parser.add_bosslet()
    parser.add_argument(
        'channel_id',
        help='Id of channel that will hold test data')

    args = parser.parse_args()

    return args



if __name__ == '__main__':
    args = parse_args()
    ds_test = TestDownsample(args.bosslet_config, args.channel_id, args.frame)
    start_args = ds_test.get_downsample_args()

    if args.cleanup:
        ds_test.delete_index_keys(session, start_args)
        ds_test.delete_data(session, start_args)
        import sys; sys.exit(0)

    if not args.leave_index:
        ds_test.delete_index_keys(session, start_args)

    if not args.noupload:
        ds_test.upload_data(start_args)

    sfn = args.bosslet_config.session.client('stepfunctions')
    resp = sfn.start_execution(
        stateMachineArn=start_args['resolution_hierarchy_sfn'],
        input=json.dumps(start_args)
    )
    print(resp)

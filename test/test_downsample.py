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

import alter_path
import argparse
import blosc
from bossutils.multidimensional import XYZ, Buffer
from bossutils.multidimensional import range as xyz_range
import boto3
import json
from lib import aws
from lib.hosts import PROD_ACCOUNT, DEV_ACCOUNT
from lib.names import AWSNames
import os
from spdb.c_lib.ndtype import CUBOIDSIZE
from spdb.spatialdb import AWSObjectStore, Cube
from spdb.project.basicresource import BossResourceBasic

"""
Script for running the downsample process against test data.

By default, fills the given coordinate frame with random data.  If coordinate
frame extents are not provided, defaults to a large frame (see parse_args()).

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

    def __init__(self, domain, chan_id, frame):
        """
        Args:
            domain (str): VPC domain such as production.boss.
            chan_id (str): Id of channel.  Use letters to avoid collisions with real data.
            frame (list[int]): Coordinate frame x/y/z stops.
        """
        self.domain = domain
        self.chan_id = chan_id
        self.account = self.get_account(domain)
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

    def get_account(self, domain):
        """
        Return the AWS account number based on the domain.  The account number is
        used to assemble the step function arns.

        Args:
            domain (str): VPC such as integration.boss.

        Returns:
            (str): AWS account number.
        """
        if domain == 'production.boss' or domain == 'integration.boss':
            return PROD_ACCOUNT
        return DEV_ACCOUNT

    def get_downsample_args(self, region):
        """
        Get arguments for starting the downsample.

        Args:
            region (str): AWS region.

        Returns:
            (dict): Arguments.
        """
        names = AWSNames(self.domain)
        sfn_arn_prefix = SFN_ARN_PREFIX_FORMAT.format(region, self.account)
        start_args = {
            # resolution_hierarchy_sfn is used by the test script, but not by the
            # actual resolution hiearchy step function that the script invokes.
            'resolution_hierarchy_sfn': '{}{}'.format(sfn_arn_prefix, names.resolution_hierarchy),

            'downsample_volume_lambda': LAMBDA_ARN_FORMAT.format(region, self.account, names.downsample_volume_lambda),

            'collection_id': 'collfake',
            'experiment_id': 'expfake',
            'channel_id': self.chan_id,
            'annotation_channel': False,
            'data_type': 'uint8',

            's3_index': names.s3_index,
            's3_bucket': names.cuboid_bucket,

            'x_start': 0,
            'y_start': 0,
            'z_start': 0,

            'x_stop': self.frame[0],
            'y_stop': self.frame[1],
            'z_stop': self.frame[2],

            'resolution': 0,
            'resolution_max': 2,
            'res_lt_max': True,

            'type': 'anisotropic',
            'iso_resolution': 3,

            'aws_region': region,
        }

        return start_args

    def upload_data(self, session, args):
        """
        Fill the coord frame with random data.

        Args:
            session (boto3.Session): Open session.
            args (dict): This should be the dict returned by get_downsample_args().
        """
        cuboid_size = CUBOIDSIZE[0]
        x_dim = cuboid_size[0]
        y_dim = cuboid_size[1]
        z_dim = cuboid_size[2]

        x_extent = ceildiv(args['x_stop'], x_dim)
        y_extent = ceildiv(args['y_stop'], y_dim)
        z_extent = ceildiv(args['z_stop'], z_dim)
        extents_in_cuboids = XYZ(x_extent, y_extent, z_extent)

        resource = BossResourceBasic()
        resource.from_dict(self.get_image_dict())
        resolution = 0
        ts = 0
        version = 0

        # DP HACK: uploading all cubes will take longer than the actual downsample
        #          just upload the first volume worth of cubes and update the activity
        #          to only use the first volume of cube data
        bucket = S3Bucket(session, args['s3_bucket'])
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
        print('.')
        print('Done uploading.')


def parse_args():
    """
    Parse command line or config file.

    Returns:
        (Namespace): Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description='Script for testing downsample process. ' + 
        'To supply arguments from a file, provide the filename prepended with an `@`.',
        fromfile_prefix_chars = '@')
    parser.add_argument(
        '--aws-credentials', '-a',
        metavar='<file>',
        default=os.environ.get('AWS_CREDENTIALS'),
        type=argparse.FileType('r'),
        help='File with credentials for connecting to AWS (default: AWS_CREDENTIALS)')
    parser.add_argument(
        '--region', '-r',
        default='us-east-1',
        help='AWS region (default: us-east-1)')
    parser.add_argument(
        '--frame', '-f',
        nargs=3,
        type=int,
        default=[277504, 277504, 1000],
        help='Coordinate frame max extents (default: 277504, 277504, 1000)')
    parser.add_argument(
        '--noupload',
        action='store_true',
        default=False,
        help="Don't upload any data to the channel")
    parser.add_argument(
        'domain',
        help='Domain that lambda functions live in, such as integration.boss')
    parser.add_argument(
        'channel_id',
        help='Id of channel that will hold test data')

    args = parser.parse_args()

    if args.aws_credentials is None:
        parser.print_usage()
        parser.exit(
            1, 'Error: AWS credentials not provided and AWS_CREDENTIALS is not defined')

    return args



if __name__ == '__main__':
    args = parse_args()
    ds_test = TestDownsample(args.domain, args.channel_id, args.frame)
    start_args = ds_test.get_downsample_args(args.region)

    session = aws.create_session(args.aws_credentials)

    if not args.noupload:
        ds_test.upload_data(session, start_args)

    sfn = session.client('stepfunctions')
    resp = sfn.start_execution(
        stateMachineArn=start_args['resolution_hierarchy_sfn'],
        input=json.dumps(start_args)
    )
    print(resp)

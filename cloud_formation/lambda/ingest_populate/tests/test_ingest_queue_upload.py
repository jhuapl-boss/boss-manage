# Copyright 2016 The Johns Hopkins University Applied Physics Laboratory
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# lambdafcns contains symbolic links to lambda functions in boss-tools/lambda.
# Since lambda is a reserved word, this allows importing from that folder 
# without updating scripts responsible for deploying the lambda code.

import boto3
import ingest_queue_upload as iqu
#import ingest_queue_upload_master as iqum
import json
import unittest
from unittest.mock import patch, MagicMock
import pprint
import ingestclient.plugins.catmaid as ic_plugs
import ingestclient.core.backend as backend

@patch('boto3.resource')
class TestIngestQueueUploadLambda(unittest.TestCase):

    def test_something(self, fake_resource):

        # This puts in a mock for boto3.resource('sqs').Queue().
        queue = MagicMock()
        #fake_resource.return_value = queue
        queue.send_messages.return_value = {'Successful': ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10']}
        fake_resource.return_value.Queue.return_value = queue
        context = None
        args = {
            "upload_sfn": "IngestUpload",
            "x_start": 0,
            "x_stop": 2048,
            "y_start": 0,
            "y_stop": 2048,
            "z_start": 0,
            "z_stop": 20,
            "t_start": 0,
            "t_stop": 1,
            "project_info": [
              "3",
              "3",
              "3"
            ],
            "ingest_queue": "https://queue.amazonaws.com/...",
            "job_id": 11,
            "upload_queue": "https://queue.amazonaws.com/...",
            "x_tile_size": 1024,
            "y_tile_size": 1024,
            "t_tile_size": 1,
            "z_tile_size": 1,
            "resolution": 0,
            "tiles_to_skip": 0,
            'MAX_NUM_TILES_PER_LAMBDA': 30000,
            'z_chunk_size': 16

        }

        actual = iqu.handler(args, context)
        self.assertEqual(80, actual)


    def test_create_messages(self, fake_resource):

        # This puts in a mock for boto3.resource('sqs').Queue().
        #queue = MagicMock()
        #fake_resource.return_value = queue
        context = None
        args = {
            "upload_sfn": "IngestUpload",
            "x_start": 0,
            "x_stop": 2048,
            "y_start": 0,
            "y_stop": 2048,
            "z_start": 0,
            "z_stop": 20,
            "t_start": 0,
            "t_stop": 1,
            "project_info": [
              "3",
              "3",
              "3"
            ],
            "ingest_queue": "https://queue.amazonaws.com/...",
            "job_id": 11,
            "upload_queue": "https://queue.amazonaws.com/...",
            "x_tile_size": 1024,
            "y_tile_size": 1024,
            "t_tile_size": 1,
            "z_tile_size": 1,
            "resolution": 0,
            "tiles_to_skip": 3,
            'MAX_NUM_TILES_PER_LAMBDA': 40,
            'z_chunk_size': 16

        }

        msg = iqu.create_messages(args)
        for i in range(45):
            try:
                print(i)
                args_ = next(msg)
                print(str(args_))
                pprint.pprint(args_)
            except StopIteration:
                break_count = i;
                break
        print("breakcount = {}".format(break_count))
        self.assertEqual(40, break_count)


    # Test for Catmaid Need to be moved to a separate test file.
    # It can't be in the same file as @patch('boto3.resource') on the top class.
    #
    # def test_catmaid(self ): #fake_resource):
    #
    #     # This puts in a mock for boto3.resource('sqs').Queue().
    #     #queue = MagicMock()
    #     #fake_resource.return_value = queue
    #     context = None
    #     args = {
    #         "upload_sfn": "IngestUpload",
    #         "x_start": 0,
    #         "x_stop": 15000,
    #         "y_start": 0,
    #         "y_stop": 15000,
    #         "z_start": 0,
    #         "z_stop": 40,
    #         "t_start": 0,
    #         "t_stop": 1,
    #         "project_info": [
    #           "3",
    #           "3",
    #           "3"
    #         ],
    #         "ingest_queue": "https://queue.amazonaws.com/...",
    #         "job_id": 11,
    #         "upload_queue": "https://queue.amazonaws.com/...",
    #         "x_tile_size": 1024,
    #         "y_tile_size": 1024,
    #         "t_tile_size": 1,
    #         "z_tile_size": 1,
    #         "resolution": 0,
    #         "tiles_to_skip": 0,
    #         'MAX_NUM_TILES_PER_LAMBDA': 20000,
    #         'z_chunk_size': 16
    #
    #     }
    #
    #     catmaidparms = {
    #       "root_dir": "/garbage",
    #       "filetype": "png",
    #       "ingest_job": {
    #         "extent": {
    #           "x": [0, 15360],
    #           "z": [0, 40],
    #           "t": [0, 1],
    #           "y": [0, 15360]
    #         },
    #         "resolution": 0,
    #         "tile_size": {
    #           "x": 1024,
    #           "z": 1,
    #           "t": 1,
    #           "y": 1024
    #         }
    #       },
    #       "schema": {
    #         "validator": "BossValidatorV01",
    #         "name": "boss-v0.1-schema"
    #       },
    #       "database": {
    #         "channel": "ingest_test_ch6_9375",
    #         "experiment": "ingest_test_exp6",
    #         "collection": "ingest_test_col6"
    #       },
    #       "client": {
    #         "tile_processor": {
    #           "params": {
    #             "filetype": "png"
    #           },
    #           "class": "ingestclient.plugins.catmaid.CatmaidFileImageStackTileProcessor"
    #         },
    #         "backend": {
    #           "host": "api-hiderrt1.thebossdev.io",
    #           "protocol": "https",
    #           "name": "boss",
    #           "class": "BossBackend"
    #         },
    #         "path_processor": {
    #           "params": {
    #             "filetype": "png",
    #             "root_dir": "/Users/hiderrt1/projects/microns/code/ingest-test/data/stack"
    #           },
    #           "class": "ingestclient.plugins.catmaid.CatmaidFileImageStackPathProcessor"
    #         }
    #       }
    #     }
    #
    #     cat_maid = ic_plugs.CatmaidFileImageStackPathProcessor()
    #     cat_maid.setup(catmaidparms)
    #     be = backend.BossBackend(None)
    #
    #     # args['z_tile_size'] = 16
    #     # args['final_z_stop'] = 40
    #     msgs = iqu.create_messages(args)
    #     for msg in msgs:
    #         msg_json = json.loads(msg)
    #         key_parts = be.decode_tile_key(msg_json['tile_key'])
    #         cat_maid.process(key_parts["x_index"],
    #                          key_parts["y_index"],
    #                          key_parts["z_index"],
    #                          key_parts["t_index"])
    #
    #     self.assertTrue(True)


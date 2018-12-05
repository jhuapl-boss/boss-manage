import boto3
import json
import time
import hashlib
import pprint
from botocore.exceptions import ClientError


class FailedToSendMessages(Exception):
    pass


SQS_BATCH_SIZE = 10
SQS_RETRY_TIMEOUT = 15


def handler(args, context):
    """Populate the ingest upload SQS Queue with tile information

    Note: This activity will clear the upload queue of any existing
          messages

    Args:
        args: {
            'job_id': '',
            'upload_queue': ARN,
            'ingest_queue': ARN,

            'resolution': 0,
            'project_info': [col_id, exp_id, ch_id],

            't_start': 0,
            't_stop': 0,
            't_tile_size': 0,

            'x_start': 0,
            'x_stop': 0,
            'x_tile_size': 0,

            'y_start': 0,
            'y_stop': 0
            'y_tile_size': 0,

            'z_start': 0,
            'z_stop': 0
            'z_tile_size': 0,

            'z_chunk_size': 16,
            'MAX_NUM_ITEMS_PER_LAMBDA': 20000
            'items_to_skip': 0
        }

    Returns:
        int: Number of messages put into the queue
    """
    print("Starting to populate upload queue")
    pprint.pprint(args)

    msgs = create_messages(args)
    # trying creating this resource after we find the first message to return.
    queue = boto3.resource('sqs').Queue(args['upload_queue'])

    sent = 0

    while True:
        batch = []
        for i in range(SQS_BATCH_SIZE):
            try:
                batch.append({
                    'Id': str(i),
                    'MessageBody': next(msgs),
                    'DelaySeconds': 0
                })
            except StopIteration:
                break

        if len(batch) == 0:
            break

        retry = 3
        while retry > 0:
            try:
                try_again = False
                resp = queue.send_messages(Entries=batch)
                if 'Successful' in resp:
                    sent += len(resp['Successful'])

                if 'Failed' in resp and len(resp['Failed']) > 0:
                    try_again = True
                    print("Batch failed to enqueue messages")
                    print("Retries left: {}".format(retry))
                    print("Boto3 send_messages response: {}".format(resp))
                    # shorten the batch to only those ids that failed.
                    ids = [f['Id'] for f in resp['Failed']]
                    batch = [b for b in batch if b['Id'] in ids]
            except ClientError as err:
                try_again = True
                print('ClientError while sending messages: {}  batch: {}'.format(err, batch))

            if try_again:
                retry -= 1
                if retry == 0:
                    print("Exhausted retry count, stopping")
                    raise FailedToSendMessages(batch)  # SFN will relaunch the activity
                time.sleep(SQS_RETRY_TIMEOUT)
                continue
            else:
                break

    return sent


def create_messages(args):
    """Create all of the tile messages to be enqueued

    Args:
        args (dict): Same arguments as populate_upload_queue()

    Returns:
        list: List of strings containing Json data
    """

    tile_size = lambda v: args[v + "_tile_size"]
    range_ = lambda v: range(args[v + '_start'], args[v + '_stop'], tile_size(v))

    # DP NOTE: generic version of
    # BossBackend.encode_chunk_key and BiossBackend.encode.tile_key
    # from ingest-client/ingestclient/core/backend.py
    def hashed_key(*args):
        base = '&'.join(map(str,args))

        md5 = hashlib.md5()
        md5.update(base.encode())
        digest = md5.hexdigest()

        return '&'.join([digest, base])

    tiles_to_skip = args['items_to_skip']
    count_in_offset = 0

    for t in range_('t'):
        for z in range(args['z_start'], args['z_stop'], args['z_chunk_size']):
            for y in range_('y'):
                for x in range_('x'):
                    num_of_tiles = min(args['z_chunk_size'], args['z_stop'] - z)

                    for tile in range(z, z + num_of_tiles):
                        if tiles_to_skip > 0:
                            tiles_to_skip -= 1
                            continue

                        if count_in_offset == 0:
                            print("Finished skipping tiles")

                        chunk_x = int(x / tile_size('x'))
                        chunk_y = int(y / tile_size('y'))
                        chunk_z = int(z / args['z_chunk_size'])
                        chunk_key = hashed_key(num_of_tiles,
                                               args['project_info'][0],
                                               args['project_info'][1],
                                               args['project_info'][2],
                                               args['resolution'],
                                               chunk_x,
                                               chunk_y,
                                               chunk_z,
                                               t)

                        count_in_offset += 1
                        if count_in_offset > args['MAX_NUM_ITEMS_PER_LAMBDA']:
                            return  # end the generator
                        tile_key = hashed_key(args['project_info'][0],
                                              args['project_info'][1],
                                              args['project_info'][2],
                                              args['resolution'],
                                              chunk_x,
                                              chunk_y,
                                              tile,
                                              t)

                        msg = {
                            'job_id': args['job_id'],
                            'upload_queue_arn': args['upload_queue'],
                            'ingest_queue_arn': args['ingest_queue'],
                            'chunk_key': chunk_key,
                            'tile_key': tile_key,
                        }

                        yield json.dumps(msg)

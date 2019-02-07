import boto3
import json
import time
import hashlib
import pprint

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
            'MAX_NUM_TILES_PER_LAMBDA': 20000
        }

    Returns:
        int: Number of messages put into the queue
    """
    print("Starting to populate upload queue")
    pprint.pprint(args)

    queue = boto3.resource('sqs').Queue(args['upload_queue'])

    msgs = create_messages(args)
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
            resp = queue.send_messages(Entries=batch)
            sent += len(resp['Successful'])

            if 'Failed' in resp and len(resp['Failed']) > 0:
                print("Batch failed to enqueue messages")
                print("Retries left: {}".format(retry))
                print("Boto3 send_messages response: {}".format(resp))
                time.sleep(SQS_RETRY_TIMEOUT)

                ids = [f['Id'] for f in resp['Failed']]
                batch = [b for b in batch if b['Id'] in ids]
                retry -= 1
                if retry == 0:
                    print("Exhausted retry count, stopping")
                    raise FailedToSendMessages(batch) # SFN will relaunch the activity
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

    # tile_size = lambda v: args[v + "_tile_size"]
    # range_ = lambda v: range(args[v + '_start'], args[v + '_stop'], tile_size(v))

    # DP NOTE: generic version of
    # BossBackend.encode_chunk_key and BiossBackend.encode.tile_key
    # from ingest-client/ingestclient/core/backend.py
    def hashed_key(*args):
        base = '&'.join(map(str,args))

        md5 = hashlib.md5()
        md5.update(base.encode())
        digest = md5.hexdigest()

        return '&'.join([digest, base])


    tile_size = lambda v: args[v + "_tile_size"]
    
    # CF  New algorithm to calculate the new starting values for T Z Y X , given # of tiles to skip

    # Helper functions 

    new_range = lambda v, vns, First : range(vns, args[v + '_stop'] , args[v + '_tile_size']) if First else range(args[v + '_start'], args[v + '_stop'] , args[v + '_tile_size'])
    new_range_z = lambda zns, First : range(zns, args['z_stop'] , args['z_chunk_size']) if First else range(args['z_start'], args['z_stop'] , args['z_chunk_size'])
    new_range_tile = lambda t2s,z,First,nt : range(z + t2s, z + nt) if First else range(z, z + nt)

    iter_ = lambda v: int((args[v + '_stop'] - args[v + '_start'] - 1) / args[v + '_tile_size']) + 1
    ns = lambda v,n: args[v + '_start'] + args[v + '_tile_size'] * n
    ns_z = lambda v,n: args[v + '_start'] + args[v + '_chunk_size'] * n

    #  Calculate new ( Tns Znz Yns Xns ) values 

    xIt = iter_('x')
    yIt = iter_('y')
    zIt = args['z_stop'] - args['z_start']

    tiles_to_skip = args['tiles_to_skip']

    kt = int(tiles_to_skip/(xIt*yIt*zIt))
    Tns = ns('t',kt)
    tiles_to_skip -= kt*xIt*yIt*zIt

    kz = int(tiles_to_skip/(args['z_chunk_size']*xIt*yIt))
    Zns = ns_z('z',kz)
    tiles_to_skip -= kz*args['z_chunk_size']*xIt*yIt

    nt = min(args['z_chunk_size'], args['z_stop'] - Zns)
    ky = int(tiles_to_skip/(nt*xIt))
    Yns = ns('y',ky)
    tiles_to_skip -= ky*nt*xIt

    kx = int(tiles_to_skip/nt)
    Xns = ns('x',kx)
    tiles_to_skip -= kx*nt

    num = 0 
    bFirst = True

    # print ("\n =====================   Next RUN of Create Messages ========================= \n")
    #print ("TEST4::  Tns: {}, Zns: {}, Yns: {}, Xns: {}".format(Tns, Zns, Yns, Xns))

    count_in_offset = 0

    #Use the new T Z Y X values to loop --- 

    for t in new_range('t',Tns,bFirst):
        for z in new_range_z(Zns,bFirst):
            num_of_tiles = min(args['z_chunk_size'], args['z_stop'] - z)

            for y in new_range('y',Yns,bFirst):
                for x in new_range('x',Xns,bFirst):

                    for tile in new_range_tile(tiles_to_skip, z, bFirst, num_of_tiles):
                        if bFirst:
                            bFirst = False
                            # print ("First POS:{:4d}, // t:{:3d}, z:{:3d}, y:{:3d}, x:{:3d}, // tile:{:3d}\n---------------- ".format(num, t, z, y, x,tile))

                        # print (" Next POS:{:4d}, // t:{:3d}, z:{:3d}, y:{:3d}, x:{:3d}, // tile:{:3d}\n---------------- ".format(num, t, z, y, x,tile))

                        num += 1

                        if count_in_offset == 0:
                            print("\n *** FINISHED SKIPPING tiles *** \n")

                        #print ("TileNum: {:4d}, t:{:3d}, // z:{:3d}, y:{:3d}, x:{:3d}, tile:{:3d}".format(num, t, z, y, x,tile))

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
                        if count_in_offset > args['MAX_NUM_TILES_PER_LAMBDA']:
                            #print ("  --- END GENERATOR --- count: {}".format(count_in_offset))
                            return  # end the generator

                        #print ("NOT returning .... {} , [{}, {}, {}] \n".format(count_in_offset, chunk_z, chunk_y, chunk_x))

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

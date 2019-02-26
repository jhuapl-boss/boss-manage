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
    
    # CF  New algorithm follows

    #  Goal is to PRE-COMPUTE the new starting values for T Z Y X , given # of tiles to skip
    #  Having the starting values will be more efficient than iterating for every TZYX

    # Tns:  T's new start position
    # Zns:  Z's new start position
    # Yns:  Y's new start position
    # Xns:  X's new start position

    #########################
    # 
    #  First, Let's create some Helper lambda functions 
    #

    # range helper function for X and Y dimensions
    new_range = lambda v, vns, First : range(vns, args[v + '_stop'] , args[v + '_tile_size']) if First else range(args[v + '_start'], args[v + '_stop'] , args[v + '_tile_size'])
    # range helper function for Z dimension
    new_range_z = lambda zns, First : range(zns, args['z_stop'] , args['z_chunk_size']) if First else range(args['z_start'], args['z_stop'] , args['z_chunk_size'])
    # range helper function for tiles
    new_range_tile = lambda t2s,z,First,nt : range(z + t2s, z + nt) if First else range(z, z + nt)

    # generic helper lambda func factoring tile_size (use ceiling)
    factor_ = lambda v: int((args[v + '_stop'] - args[v + '_start'] - 1) / args[v + '_tile_size']) + 1

    # new start helper func (for tile_size cases)
    ns = lambda v,n: args[v + '_start'] + args[v + '_tile_size'] * n
    # new start helper func for special case Z (which uses chunk_size)
    ns_z = lambda v,n: args[v + '_start'] + args[v + '_chunk_size'] * n

    ##########################
    #
    # Now Let's start the actual calculations to compute the new ( Tns Znz Yns Xns ) values 
    #

    # first, factor in  (x, y, z dimensions)
    Xf = factor_('x')
    Yf = factor_('y')
    Zf = args['z_stop'] - args['z_start']

    # counter to keep track of # tiles to skip, used decrementally throughout the rest of the calcs below
    tiles_to_skip = args['tiles_to_skip']

    ############### T
    # T pos, factoring in X, Y, Z
    Tk = int(tiles_to_skip/(Xf*Yf*Zf))
    #compute T's new start
    Tns = ns('t',Tk)
    #decr tiles to skip
    tiles_to_skip -= Tk*Xf*Yf*Zf

    ############### Z
    # Z pos, factoring in X, Y
    Zk = int(tiles_to_skip/(args['z_chunk_size']*Xf*Yf))
    # compute Z's new start
    Zns = ns_z('z',Zk)
    # decr tiles to skip
    tiles_to_skip -= Zk*args['z_chunk_size']*Xf*Yf

    #set the number of tiles (to be used for X and Y calculations)
    num_tiles = min(args['z_chunk_size'], args['z_stop'] - Zns)

    ############### Y
    # Y pos, factoring in X
    Yk = int(tiles_to_skip/(num_tiles*Xf))
    # compute Y's new start pos
    Yns = ns('y',Yk)
    # decr tiles to skip
    tiles_to_skip -= Yk*num_tiles*Xf

    ############### X
    # X pos, factoring in num tiles
    Xk = int(tiles_to_skip/num_tiles)
    # compute X's new start pos
    Xns = ns('x',Xk)
    # decr tiles to skip
    tiles_to_skip -= Xk*num_tiles


    #######################################
    # 
    #  Now that we've computed the new start values (Tns, Zns, Yns, Xns) and the tiles_to_skip, 
    # ... let's begin our "efficient" LOOPING! 
    #

    #first, initialize vars 
    num = 0 
    bFirst = True
    count_in_offset = 0    

    for t in new_range('t', Tns, bFirst):
        for z in new_range_z(Zns, bFirst):
            #Factor in Z chunk size
            num_of_tiles = min(args['z_chunk_size'], args['z_stop'] - z)

            for y in new_range('y', Yns, bFirst):
                for x in new_range('x', Xns, bFirst):

                    for tile in new_range_tile(tiles_to_skip, z, bFirst, num_of_tiles):
                        if bFirst:
                            bFirst = False
                        num += 1

                        if count_in_offset == 0:
                            print(" **** FINISHED SKIPPING tiles *** \n")

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

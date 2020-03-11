# Cutout Service - Last Updated 2Mar2020

**Note, this writeup was generated while investigating keys stuck in a PAGE-OUT
set (write caching).  The descriptions of read caching may be incomplete or not
entirely accurate.**

The cutout service allows for arbitrary reading or writing of cuboid data.
Reads and writes do not have to be cuboid aligned or even full cuboids.


## Lookup Key

The lookup key will be referenced many times in this document.  This key
identifies the collection, experiment, and channel that a cuboid belongs to.

Key Format: <collection id>&<experiment id>&<channel id>


## Redis Caches

### KVIO Cache

This cache contains actual cuboid data to speed up reading and temporarily
store new cuboid data before writing to the S3 cuboid bucket.

Data meant to be written to the S3 cuboid bucket is keyed by WRITE-CUBOID keys.
Data for speeding up cuboid reads is keyed by CACHED-CUBOID keys.

Code for this cache lives in `spdb.git/spdb/spatialdb/rediskvio.py`.


#### WRITE-CUBOID Keys

Key Format: WRITE-CUBOID&<lookup key>&<resolution>&<time sample>&<morton id>

These keys identify actual cuboid data to be written to S3.


#### CACHED-CUBOID Keys

Key Format: CACHED-CUBOID&<lookup key>&<resolution>&<time sample>&<morton id>

These keys identify cached cuboid data available for reading.


### State Cache

This cache tracks work that needs to be done for writing cuboids to S3 or for
reading cuboids from S3 into the cache.

Code for this cache lives in `spdb.git/spdb/spatialdb/state.py`.


#### DELAYED-WRITE Keys

Key Format: DELAYED-WRITE&<lookup key>&<resolution>&<time sample>&<morton id>

Each DELAYED-WRITE key has an ordered queue of write cuboid keys that all
update the same cuboid.  The write cuboid keys map to the actual cuboid data
stored in the KVIO cache.

During a page out, the first WRITE-CUBOID key in the DELAYED-WRITE key's queue
will be passed to the S3 flush lambda and the writes will be merged and
written to the S3 cuboid bucket.


#### RESOURCE Keys

Key Format: RESOURCE-DELAYED-WRITE&<lookup key>&<resolution>&<time sample>&<morton>

Whenever a DELAYED-WRITE key is created, a correspond RESOURCE key is also
created.  The RESOURCE key holds a JSON string with additional information
about the collection, experiment, and channel that the cuboid belongs to.


#### PAGE-OUT Keys

Key Format: PAGE-OUT&<lookup key>&<resolution>

When a cuboid is marked to be written from the Redis to the S3 cuboid bucket,
its DELAYED-WRITE key is added to a set identified by a PAGE-OUT key.  No
other writes for that same cuboid can happen while there is a corresponding
DELAYED-WRITE key in the PAGE-OUT set.


### PREFETCH Key

This is a Redis queue that contains the S3 object keys of cuboids to load.


### WRITE-LOCK Keys

Key Format: WRITE-LOCK&<lookup key>

These keys mark channels that are write locked.  This happens when an S3 flush
lambda fails and its invocation event data ends up in the deadletter queue.


### PAGE-IN-CHANNEL

Format: PAGE-IN-CHANNEL&<uuid4>

These are Redis channels for publishing and subscribing to messages.  The state
cache creates and subscribes to channels to wait for cuboids to be paged in
from S3.


## Cache Manager

This is an EC2 instance which periodically checks the Redis caches via daemons.
Code for these daemons lives in `boss-tools.git/cachemgr`.


### boss\_delayedwrited.py

This daemon checks all the DELAYED-WRITE keys and tries to start paging them
out if the key is not currently part of a PAGE-OUT set.  If it succeeds in
starting a page out, it does so by enqueuing a message to the S3 flush queue.
The message contains the first WRITE-CUBOID key in the DELAYED-WRITE queue
and information about the collection, experiment, and channel constructed from
corresponding data in the RESOURCE key.  After enequing the message, the
daemon invokes the S3 flush lambda.


### boss\_cachemissd.py

On a read cache miss, also trigger loading of the cuboid above and below (on
the Z axis) the cuboid that was just read.  It populates the PREFETCH queue in
the Redis state cache.


### boss\_deadletterd.py

This daemon checks the deadletter queue that is populated by failed S3 flush
lambdas.  It will lock the channel for writing if it finds messages from
failed S3 flush lambdas.  An SNS alert will be sent after write locking a
channel.


### boss\_prefetchd.py

This daemon loads cuboids from S3 into the KVIO cache by triggering the page-in
lambda.  The PREFETCH queue in the Redis state cache is serviced by this
daemon.


### boss\_sqs\_watcherd.py

The S3 flush queue is monitored by this daemon.  It invokes additional S3 flush
lambdas to ensure that the flush queue is eventually drained.


## Lambdas

These lambdas service cutouts.  Code lives in `boss-tools.git/lambdas`.

### S3 Flush Lambda

This lambda uses both the KVIO cache and the state cache to write cuboid data
to the S3 cuboid bucket.  It reads from the SQS flush queue to get the initial
job details and gets the rest of the information from the Redis caches.

The lambda tries to get all the writes for the cuboid and merge them all into
a single write to the S3 cuboid bucket.  When it finishes writing to S3, it:

1. If the cuboid exists in the **read** cache, it updates the cached data
2. Removes the cuboid data from the KVIO **write** cache
3. Removes the WRITE-CUBOID key from the PAGE-OUT set
4. Deletes the message from the SQS flush queue


### Page In Lambda

Loads the specified cuboid from S3 into the KVIO cache.  It sends a notifiation
to the PAGE-IN-CHANNEL, in the state cache, that the cuboid was loaded.

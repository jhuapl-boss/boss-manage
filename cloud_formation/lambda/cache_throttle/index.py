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

import redis
from datetime import datetime, timedelta

def handler(event, context):
    ageOffDays = 30  # default
    if 'ageOffDays' in event:
        ageOffDays = int(event['ageOffDays'])
    oldestDate = datetime.today() - timedelta(days=ageOffDays)
    print("Aging off metrics dated {} and older".format(datetime.date(oldestDate)))
    
    # look for keys older than ageOffDays
    conn = redis.StrictRedis(event['host'], 6379, 0)
    
    while True:
        datePattern = "*{}*".format(datetime.date(oldestDate))
        keys = conn.keys(pattern=datePattern)
        if not keys:
            break
        conn.delete(*keys)
        print("Deleted keys: {}".format(keys))
        oldestDate -= timedelta(days=1)
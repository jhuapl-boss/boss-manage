#!/usr/bin/env python3

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

"""
Takes Athena generated CSV file with lookup_key and total_size and generate a
new CSV file that adds the names of the collection, experiment, and channel
to each row.

Output is intended for determining how much data is in S3 for each channel.
"""

import argparse
import alter_path
import csv
from lib import boss_rds
from lib import configuration
import logging

def run(bosslet, in_file, out_file):
    """
    Main worker function.

    Args:
        bosslet_config (BossConfiguration): Bosslet configuration object.
        in_file (str): Path to input CSV file.
        out_file (str): Path to output CSV file.
    """
    keys = []
    with open(in_file, 'rt') as f:
        reader = csv.DictReader(f)
        for row in reader:
            keys.append(strip_resolution(row['lookup_key']))

    names = boss_rds.sql_get_names_from_lookup_keys(bosslet, keys)

    fields = ['lookup_key', 'total_size', 'collection', 'experiment', 'channel']
    with open(out_file, 'wt') as out:
        writer = csv.DictWriter(out, fields)
        writer.writeheader()
        with open(in_file, 'rt') as f:
            reader = csv.DictReader(f)
            for (row, row_names) in zip(reader, names):
                writer.writerow({
                    'lookup_key': row['lookup_key'],
                    'total_size': row['total_size'],
                    'collection': row_names[0],
                    'experiment': row_names[1],
                    'channel': row_names[2]
                })

def strip_resolution(key):
    """
    Removes the resolution from the lookup key.

    Args:
        (str): Lookup key (col&exp&chan&resolution).

    Returns:
        (str)
    """
    return key.rsplit('&', 1)[0]

def create_parser():
    """
    Setup the arg parser.

    Returns:
        (ArgumentParser)
    """
    parser = configuration.BossParser(
        description='Adds collection, experiment, and channel names to S3 channel usage data.',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("--quiet", "-q",
                        action='store_true',
                        default=False,
                        help='Run the script quietly, no log statements will be displayed.')

    parser.add_bosslet()

    parser.add_argument('input_csv', help='Channel usage CSV file')
    parser.add_argument('output_csv', help='New file with names added')
    return parser


if __name__ == '__main__':
    parser = create_parser()
    args = parser.parse_args()

    if not args.quiet:
        logging.basicConfig(level=logging.INFO)
    logging.getLogger('lib.boss_rds').setLevel(logging.ERROR)

    run(args.bosslet_config, args.input_csv, args.output_csv)
    logging.info('Done.')

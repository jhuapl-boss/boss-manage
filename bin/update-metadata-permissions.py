#!/usr/bin/env python3

from intern.remote.boss import BossRemote
from intern.resource.boss.resource import *
from tqdm.auto import tqdm
import time

rmt = BossRemote()
PRIMARY_USER_GROUPS = [x for x in rmt.list_groups() if '-primary' in x]

def confirm_prompt(question: str) -> bool:
    reply = None
    while reply not in ("y", "n"):
        reply = input(f"{question} (y/n): ").casefold()
    return (reply == "y")

def update_group_permissions(resource):
    existing_perms = rmt.list_permissions(resource=resource)
    for perm_set in existing_perms:
        new_perms = []
        if "read" in perm_set['permissions']:
            new_perms.append('read_metadata')
        if "add" in perm_set['permissions']: 
            # This means that this is a write or admin user for this resource
            new_perms.extend(['add_metadata', 'update_metadata', 'delete_metadata'])
        if new_perms:
            print(f"Adding {new_perms} for {perm_set['group']} to {resource.name}")
            rmt.add_permissions(perm_set['group'], resource=resource, permissions=new_perms)

def update_primary_permissions(resource):
    for group in PRIMARY_USER_GROUPS:
        new_perms = []
        existing_perms = rmt.get_permissions(group, resource)

        if "read" in existing_perms:
            new_perms.append('read_metadata')
        if "add" in existing_perms: 
            new_perms.extend(['add_metadata', 'update_metadata', 'delete_metadata'])
        if new_perms:
            print(f"Adding {new_perms} for {group} to {resource.name}")
            rmt.add_permissions(group, resource=resource, permissions=new_perms)


def main():
    for coll_name in tqdm(rmt.list_collections()):
        coll = CollectionResource(coll_name)
        update_group_permissions(coll)
        update_primary_permissions(coll)
        for exp_name in rmt.list_experiments(coll_name):
            exp = ExperimentResource(exp_name, coll_name)
            update_group_permissions(exp)
            update_primary_permissions(exp)
            for chan_name in rmt.list_channels(coll_name, exp_name):
                chan = ChannelResource(chan_name, coll_name, exp_name)
                update_group_permissions(chan)
                update_primary_permissions(chan)

if __name__ == '__main__':
    if confirm_prompt("""
Make sure to check your intern.cfg file! 
Are you sure you want to update ALL permissions?
    """
    ):
        start = time.time()
        main()
        print(f"Total time: {round(time.time() - start, 2)}")
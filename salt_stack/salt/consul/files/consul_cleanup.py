#!/usr/local/bin/python3

import bossutils
import subprocess
import shlex

log = bossutils.logger.BossLogger().logger

CONSUL = "/usr/sbin/consul"

def run(cmd):
    output = subprocess.run(shlex.split(cmd),
                            stdout=subprocess.PIPE,
                            universal_newlines=True)

    return output.stdout.split("\n")

try:
    members = run(CONSUL + " members")
    for member in members:
        #print(member)
        if 'failed' in member:
            id = member.split()[0]
            cmd = CONSUL + " force-leave " + id
            log.debug(cmd)
            run(cmd)

    peers = run(CONSUL + " operator raft -list-peers")
    for peer in peers:
        #print(peer)
        if 'unknown' in peer:
            addr = peer.split()[2]
            cmd = CONSUL + " operator raft -remove-peer -address=" + addr
            log.debug(cmd)
            run(cmd)
except:
    log.exception("Problem cleaning up the consul cluster")
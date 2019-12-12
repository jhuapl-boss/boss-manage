#!/bin/sh

usage() {
echo "Usage: $0 <bosslet> <secret/path> [<key>]"
echo ""
echo "Under the hood bastion.py is called, so make sure your environmental"
echo "variables are setup correctly for it to connect to the target domain"
echo ""
echo "       <bosslet>      Name of bosslet configuration file"
echo "       <secret/path>  Vault path to read data from"
echo "       <key>          Key at path to copy data into the system clip board"
}

if [ "$#" -lt 2 ] ; then
    usage
    exit 1
fi

BOSSLET=$1
SECRET=$2
KEY=${3:-"password"}
CB=""

which xclip > /dev/null
if [ $? -eq 0 ] ; then
    CB="xclip -selection clipboard"
fi

which pbcopy > /dev/null
if [ $? -eq 0 ] ; then
    CB="pbcopy"
fi


if [ -z "$CB" ] ; then
    echo "Couldn't locate xclip or pbcopy"
    exit 1
fi

python3 bastion.py vault.$BOSSLET vault-read $SECRET | ./pq .data.$KEY | $CB

#!/bin/bash

PROFILE_FILE=${PROFILE_FILE:-"${HOME}/.aws/credentials"}

if [ $# -lt 1 ] ; then
    echo "Usage: $0 <action>"
    exit 1
fi

ACTION=$1

if [ "$ACTION" == "list" ] ; then
    echo "Current profiles:"
    grep -E "\[.+\]" $PROFILE_FILE | tr -d "[]" | sed -e 's/_inactive/ (inactive)/'
    exit 0
fi

if [ $# -ne 2 ] ; then
    echo "Usage: $0 <activate | deactivate> <profile | all>"
    exit 1
fi

PROFILE=$2
if [ "$PROFILE" != "all" ] ; then
    COUNT=`grep -c -E "\[${PROFILE}(_inactive)?\]" $PROFILE_FILE`
    if [ "$COUNT" == "0" ] ; then
        echo "Profile '${PROFILE}' is not valid"
        exit 2
    fi
fi

case "${ACTION}-${PROFILE}" in
    activate-all) sed -i -e "s/\[\(.*\)_inactive\]/\[\1\]/" $PROFILE_FILE ;;
    activate-*) sed -i -e "s/\[${PROFILE}_inactive\]/\[${PROFILE}\]/" $PROFILE_FILE ;;
    deactivate-all) sed -i -e "s/\[\(.*\)\]/\[\1_inactive\]/" $PROFILE_FILE ;;
    deactivate-*) sed -i -e "s/\[${PROFILE}\]/\[${PROFILE}_inactive\]/" $PROFILE_FILE ;;
    *) echo "foobar" ;;
esac

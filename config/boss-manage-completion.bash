#!/usr/bin/env bash

_cloudformation_completions()
{
    DIR=`dirname ${COMP_WORDS[0]}`
    COMPREPLY=(`python3 $DIR/boss-manage-completion.py ${COMP_CWORD} ${COMP_WORDS[@]}`)
}

complete -F _cloudformation_completions cloudformation.py

#!/usr/bin/env python3

# Copyright 2016 The Johns Hopkins University Applied Physics Laboratory
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

"""A script for manipulating a Vault instance.

COMMANDS : A dictionary of available commands and the functions to call

Author:
    Derek Pryor <Derek.Pryor@jhuapl.edu>
"""

import argparse
import sys
import os
import json
from pprint import pprint

import alter_path
from lib.vault import Vault
from lib.utils import open_

NEW_TOKEN = "new_token"

def vault_init(vault):
    """Initialize a new Vault instance

    Args:
        vault (Vault) : Vault connection to use
    """
    vault.initialize()

def vault_configure(vault):
    """Configure a new Vault instance

    Args:
        vault (Vault) : Vault connection to use
    """
    vault.configure()

def vault_unseal(vault):
    """Unseal a Vault instance

    Args:
        vault (Vault) : Vault connection to use
    """
    vault.unseal()

def vault_seal(vault):
    """Seal a Vault instance

    Args:
        vault (Vault) : Vault connection to use
    """
    vault.seal()

def vault_status(vault):
    """Print the status of a Vault instance

    Args:
        vault (Vault) : Vault connection to use
    """
    vault.status()

def vault_shell(vault):
    """Drop into a Python REPL session with a Vault connection

    Args:
        vault (Vault) : Vault connection to use
    """
    vault.shell()

def vault_provision(vault, policy = None):
    """Create a new Vault access token.

    Command line version of vault-provision. If policy is not given, then
    prompt the user for the policy and then save to NEW_TOKEN file.

    Args:
        vault (Vault) : Vault connection to use
        policy (None|string) : Name of the policy to attach to the new token
                               If policy is None then the user is prompted for the policy name
    """
    if policy is None:
        policy = input("policy: ")
    token = vault.provision(policy)

    token_file = vault.path(NEW_TOKEN)
    print("Provisioned Token saved to {}".format(token_file))
    with open(token_file, "w") as fh:
        fh.write(token)

def vault_revoke(vault, token = None):
    """Revoke a Vault access token.

    Command line version of vault-revoke. If token is not given, then
    prompt the user for the token to revoke

    Args:
        vault (Vault) : Vault connection to use
        token (None|string) : String containing the Vault token to revoke
                              If token is None then the user is prompted for the token value
    """
    if token is None:
        token = input("token: ") # prompt for token or ready fron NEW_TOKEN (or REVOKE_TOKEN)?
    vault.revoke(token)

def vault_write(vault, path = None, *args):
    """A generic method for writing data into Vault.

    Command line version of vault-write. If the path or arguments are not given,
    then prompt the user for the path and data to store.

        Note: vault-write will override any data already existing at path.
              There is vault-update that will update data at path instead.

    Args:
        vault (Vault) : Vault connection to use
        path (None|string) : Vault path to write data to
                             if path is None then the user is prompted for the Vault path
        args : List of "key=value" strings, that will be split and processed into a dict
               if args is empty, the user will be prompted (one key/value at a time)
               for the data to store at path.
    """
    if path is None:
        path = input("path: ")
    entries = {}
    if len(args) == 0:
        while True:
            entry = input("entry (key=value): ")
            if entry is None or entry == '':
                break
            key,val = entry.split("=")
            entries[key.strip()] = val.strip()
    else:
        for arg in args:
            key,val = arg.split("=")
            entries[key.strip()] = val.strip()

    vault.write(path, **entries)

def vault_update(vault, path = None, *args):
    """A generic method for adding/updating data to/in Vault.

    Command line version of vault-update. If the path or arguments are not given,
    then prompt the user for the path and data to store.

    Args:
        vault (Vault) : Vault connection to use
        path (None|string) : Vault path to write data to
                             if path is None then the user is prompted for the Vault path
        args : List of "key=value" strings, that will be split and processed into a dict
               if args is empty, the user will be prompted (one key/value at a time)
               for the data to store at path.
    """
    if path is None:
        path = input("path: ")
    entries = {}
    if len(args) == 0:
        while True:
            entry = input("entry (key=value): ")
            if entry is None or entry == '':
                break
            key,val = entry.split("=")
            entries[key.strip()] = val.strip()
    else:
        for arg in args:
            key,val = arg.split("=")
            entries[key.strip()] = val.strip()

    vault.update(path, **entries)

def vault_read(vault, path = None):
    """A generic method for reading data from Vault.

    Command line version of vault-read. If the path is not given, then prompt
    the user for the path.

    Args:
        vault (Vault) : Vault connection to use
        path (string) : Vault path to read data from
                        if path is None then the user is prompted for the Vault path
    """

    if path is None:
        path = input("path: ")
    results = vault.read(path)
    pprint(results)

def vault_delete(vault, path = None):
    """A generic method for deleting data from Vault.

    Command line version of vault-delete. If the path is not given, then prompt
    the user for the path.

    Args:
        vault (Vault) : Vault connection to use
        path (string) : Vault path to delete all data from
                        if path is None then the user is prompted for the Vault path
    """
    if path is None:
        path = input("path: ")
    vault.delete(path)

def vault_export(vault, output='-', path="secret/"):
    """A generic method for exporting data from Vault

    Note: output data is Json encoded

    Args:
        vault (Vault) : Vault connection to use
        output (string) : Output path to save the data ('-' for stdout)
        path (string) : Vault path to export data from
    """
    rtn = vault.export(path)

    with open_(output, 'w') as fh:
        json.dump(rtn, fh, indent=3, sort_keys=True)

def vault_import(vault, input_='-'):
    """A generic method for importing data into Vault

    Note: input data should be Json encoded

    Args:
        input_ (string) : Input path to read data from ('-' for stdin)
    """
    with open_(input_) as fh:
        exported = json.load(fh)

    vault.import_(exported)

COMMANDS = {
    "vault-init": vault_init,
    "vault-configure": vault_configure,
    "vault-unseal": vault_unseal,
    "vault-seal": vault_seal,
    "vault-status": vault_status,
    "vault-provision": vault_provision,
    "vault-revoke": vault_revoke,
    "vault-shell":vault_shell,
    "vault-write":vault_write,
    "vault-update":vault_update,
    "vault-read":vault_read,
    "vault-delete":vault_delete,
    "vault-export": vault_export,
    "vault-import": vault_import,
}

if __name__ == '__main__':
    os.chdir(os.path.abspath(os.path.dirname(__file__)))

    def create_help(header, options):
        """Create formated help."""
        return "\n" + header + "\n" + \
               "\n".join(map(lambda x: "  " + x, options)) + "\n"

    commands = list(COMMANDS.keys())
    commands_help = create_help("command supports the following:", commands)

    parser = argparse.ArgumentParser(description = "Script for manipulating Vault instances",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=commands_help)
    parser.add_argument("--machine", "-m", help = "The name of the Vault server, used to read/write tokens and keys.")
    parser.add_argument("command",
                        choices = commands,
                        metavar = "command",
                        help = "Command to execute")
    parser.add_argument("arguments",
                        nargs = "*",
                        help = "Arguments to pass to the command")

    args = parser.parse_args()

    if args.command in COMMANDS:
        COMMANDS[args.command](Vault(args.machine), *args.arguments)
    else:
        parser.print_usage()
        sys.exit(1)

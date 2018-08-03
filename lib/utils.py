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

import sys
import os
import subprocess
import shlex
import getpass
import string

from contextlib import contextmanager

@contextmanager
def open_(filename, mode='r'):
    """Custom version of open that understands stdin/stdout"""
    is_std = filename is None or filename == '-'
    if is_std:
        if 'r' in mode:
            fh = sys.stdin
        else:
            fh = sys.stdout
    else:
        fh = open(filename, mode)

    try:
        yield fh
    finally:
        if not is_std:
            fh.close()


def get_command(action=None):
    argv = sys.argv[:]
    if action:
        # DP HACK: hardcoded list of supported actions, should figure out something else
        actions = ["create", "update", "delete", "post-init", "pre-init", "generate"]
        argv = [action if a in actions else a for a in argv]

    return " ".join(argv)

def json_sanitize(data):
    return (data.replace('"', '\"')
                .replace('\\', '\\\\'))

def python_minifiy(file):
    """Outputs a minified version of the given Python file.

    Runs pyminifier on the given file.  The minified filename has '.min'
    added before the '.py' extension.  This function is used to help code
    fit under the 4k limit when uploading lambda functions, directly, as
    opposed to pointing to a zip file in S3.  The minification process
    strips out all comments and uses minimal whitespace.

    Example: lambda.py => lambda.min.py

    Args:
        file (string): File name of Python file to minify.

    Returns:
        (string): File name of minified file.

    Raises:
        (subprocess.CalledProcessError): on a non-zero return code from pyminifier.
    """
    file_parts = os.path.splitext(file)
    min_filename = file_parts[0] + '.min' + file_parts[1]
    cmd = 'pyminifier -o ' + min_filename + ' ' + file
    result = subprocess.run(
        shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print(result.stderr)
    # Package up exception with output and raise if there was a failure.
    result.check_returncode()
    return min_filename

def get_commit():
    """Get the git commit hash of the current directory.

    Returns:
        (string) : The git commit hash or "unknown" if it could not be located
    """
    try:
        cmd = "git rev-parse HEAD"
        result = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE)
        return result.stdout.decode("utf-8").strip()
    except:
        return "unknown"

def keypair_to_file(keypair):
    """Looks for the SSH private key for keypair under ~/.ssh/

    Prints an error if the file doesn't exist.

    Args:
        keypair (string) : AWS keypair to locate a private key for

    Returns:
        (string|None) : SSH private key file path or None is the private key doesn't exist.
    """
    file = os.path.expanduser("~/.ssh/{}.pem".format(keypair))
    if not os.path.exists(file):
        print("Error: SSH Key '{}' does not exist".format(file))
        return None
    return file


def password(what):
    """Prompt the user for a password and verify it.

    If password and verify don't match the user is prompted again

    Args:
        what (string) : What password to enter

    Returns:
        (string) : Password
    """
    while True:
        pass_ = getpass.getpass("{} Password: ".format(what))
        pass__ = getpass.getpass("Verify {} Password: ".format(what))
        if pass_ == pass__:
            return pass_
        else:
            print("Passwords didn't match, try again.")


def generate_password(length=16):
    """Generate an alphanumeric password of the given length.

    Args:
        length (int) : length of the password to be generated

    Returns:
        (string) : password
    """
    chars = string.ascii_letters + string.digits  #+ string.punctuation
    return "".join([chars[c % len(chars)] for c in os.urandom(length)])

def find_dict_with(list_of_dicts, key, value):
    """
    finds the first dictionary containing the key, value pair.
    Args:
        list_of_dicts: a list of dictionaries
        key:  key to search for in the dictionaries
        value:  the value that should be assigned to the key

    Returns:
        returns the first dictionary containing the key,value pair.
    """
    for d in list_of_dicts:
        if key in d:
            if d[key] == value:
                return d;
    return None

def get_user_confirm(message):
    """
    General method to warn the user to read the message before proceeding
    and prompt a yes or no answer.
    
    Args:
        message(str): The message which will be showed to the user.
    
    Returns:
        returns True if user confirms with yes
    """
    resp = input(message + " [y/N]")
    if len(resp) == 0 or resp[0] not in ('y', 'Y'):
        print("Canceled")
        return False
    else:
        return True

class console:
    """
        Used to add coloring to terminal print statements
    """

    @staticmethod
    def warning(message):
        print('\033[93m' + message +'\033[0m')

    @staticmethod
    def okgreen(message):
        print('\033[92m' + message +'\033[0m')

    @staticmethod
    def okblue(message):
        print('\033[94m' + message +'\033[0m')

    @staticmethod
    def fail(message):
        print('\033[91m' + message +'\033[0m')
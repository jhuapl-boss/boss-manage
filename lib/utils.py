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
import warnings
import time

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

    Runs pyminify on the given file.  The minified filename has '.min'
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
    # The no-rename-locals, no-convert-posargs-to-argsoptions could be removed
    # to get smaller filesizes at the cost of readability
    minify_options = ' --no-rename-locals --no-convert-posargs-to-args --remove-literal-statements '
    min_filename = file_parts[0] + '.min' + file_parts[1]
    cmd = 'pyminify ' + minify_options + file
    result = subprocess.run(
        shlex.split(cmd), capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr)
    with open(min_filename, "w") as fh:
        fh.write(result.stdout)
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

def get_submodule_commit(submodule_path):
    try:
        cmd = "git submodule status"
        result = subprocess.run(shlex.split(cmd), stdout=subprocess.PIPE)
        for line in result.stdout.decode("utf-8").splitlines():
            if submodule_path in line:
                commit, _ = line.strip().split(' ', 1)

                # Remove the indicator that the commit was changed but not committed
                if commit[0] == '+':
                    commit = commit[1:]

                return commit
    except:
        pass

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

def deprecated(msg = "The called function is now deprecated"):
    warnings.warn(msg, DeprecationWarning, stacklevel=2)

def parse_hostname(hostname):
    # handle one of the following
    # - index.machine_name.bosslet_name
    # - index.machine_name
    # - machine_name.bosslet_name
    # - machine_name
    # where bosslet_name may contain a '.'

    # NOTE: Doesn't support passing an IP address

    # split out the index, machine name, and bosslet name
    try:
        # assume index.machine.bosslet
        tmp = hostname.split(".", 1)
        idx = int(tmp[0])
        try:
            _, machine, bosslet_name = hostname.split(".", 2)
        except ValueError: # assume no bosslet_name
            # handle just index.machine
            _, machine = tmp
            bosslet_name = None
    except ValueError: # assume no index
        idx = None
        try:
            # handle just machine.bosslet
            machine, bosslet_name = tmp
        except ValueError: # assume no bosslet_name
            # handle just machine
            machine, bosslet_name = tmp[0], None

    return (idx, machine, bosslet_name)

def run(cmd, input=None, env_extras=None, checkreturn=True, shell=False, **kwargs):
    """Run a command and stream the output

    Args:
        cmd (str): String with the command to run
        input (optional[str]): String with data to sent to the processes stdin
        env_extras (optional[dict]): Dictionary of extra environmental variable to provide
        checkreturn (bool): If the return code should be checked and an exception raised if not zero
        kwargs: Other arguments to pass to the Popen constructor

    Return:
        int: The return code of the process

    Raises:
        Exception: If checkreturn is True and the return code is 0 (zero)
    """

    if env_extras is not None:
        env = os.environ.copy()
        env.update(env_extras)
    else:
        env = None

    proc = subprocess.Popen(shlex.split(cmd) if not shell else cmd,
                            env=env,
                            shell=shell,
                            bufsize=1, # line bufferred
                            #universal_newlines=True, # so we don't have to encode/decode
                            stderr=subprocess.STDOUT,
                            stdout=subprocess.PIPE,
                            stdin=subprocess.PIPE if input is not None else None,
                            **kwargs)

    if input is not None:
        proc.stdin.write(cmd.encode())
        proc.stdin.close()

    for line in proc.stdout:
        print(line.decode('utf8'), end='', flush=True)

    while proc.poll() is None:
        time.sleep(1) # sometimes stdout is closed before the process has completely finished

    if checkreturn:
        if proc.returncode != 0:
            raise Exception("Return code: {}".format(proc.returncode))

    return proc.returncode

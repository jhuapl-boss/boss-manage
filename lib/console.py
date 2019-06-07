# Copyright 2019 The Johns Hopkins University Applied Physics Laboratory
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
A library for interacting with the user and their terminal. All methods in this
library can detect when output is being piped or redirected and will change their
behavior so their don't omit escape codes.
"""

import sys
import signal
import shutil
import colorama
from colorama import Fore, Style

def init():
    colorama.init()

def _colorize(*style_msg, **kwargs):
    print(*style_msg, sep='', **kwargs)

def red(msg, **kwargs):
    return _colorize(Fore.RED, msg, Style.RESET_ALL, **kwargs)

def yellow(msg, **kwargs):
    return _colorize(Fore.YELLOW, msg, Style.RESET_ALL, **kwargs)

def green(msg, **kwargs):
    return _colorize(Fore.GREEN, msg, Style.RESET_ALL, **kwargs)

def blue(msg, **kwargs):
    return _colorize(Fore.BLUE, msg, Style.RESET_ALL, **kwargs)

def fail(msg, **kwargs):
    return red(' FAIL: ' + msg, **kwargs)

def error(msg, **kwargs):
    return red('ERROR: ' + msg, **kwargs)

def warning(msg, **kwargs):
    return yellow(' WARN: ' + msg, **kwargs)

def info(msg, **kwargs):
    return blue(' INFO: ' + msg, **kwargs)

def debug(msg, **kwargs):
    return green('DEBUG: ' + msg, **kwargs)

def _raise_timeout(signum, frame):
    """Signal handler that always raises a TimeoutError"""
    raise TimeoutError()

def confirm(message, default = False, timeout = None):
    """
    General method to warn the user to read the message before proceeding
    and prompt a yes or no answer.

    If stdout is piped a timeout will be set (if not provided) so that the
    script doesn't hang waiting for input. A timeout is used so that a user
    can use `python3 script.py > script.log` and have the script take the
    default action for all prompts.

    If the user wants to answer `yes` to all of the prompts they can use
    `yes | python3 script.py` to automatically answer the prompts.
    
    Args:
        message (str): The message which will be showed to the user.
        default (bool): Denoting if yes or no should be the default response
        timeout (optional[int]): Number of seconds to wait before returning the
                                 default value
    
    Returns:
        returns True if user confirms with yes
    """
    if not sys.stdout.isatty():
        # If stdout is piped (often meaning that no user is available for a
        # response) then set a short timeout. The timeout allows (instead of
        # just returning the default value) so that this function works correctly
        # when running under `yes | python3 script.py > script.log`
        if timeout is None:
            timeout = 3

    if timeout is not None:
        signal.signal(signal.SIGALRM, _raise_timeout)
        signal.alarm(timeout)

    try:
        suffix = " [{}/{}]: ".format("Y" if default else "y",
                                    "n" if default else "N")
        resp = input(message + suffix)
        if not sys.stdin.isatty():
            # If stdin is piped (often from `yes`) then print the response so
            # that is shows up in the logs (as it was not typed in the screen)
            print(resp)

        if len(resp) == 0:
            return default
        else:
            return resp[0] in ('y', 'Y')
    except TimeoutError:
        print(" (timeout)") # since user didn't hit <enter>
        return default
    finally:
        if timeout is not None:
            signal.alarm(0)

class status_line(object):
    """An object or context manager for displaying a status line that always
    stays at the bottom of the screen.

    Note: This object will override any text on the current line

    Note: This object also acts as a stdout replacement, so that it can
          intercept calls to `write()` and correctly handle moving the
          status line

    Note: This object correctly handles if stdout is piped or redirected and
          will only display the status line when it is first updated

    Note: This context manager can be nested with only the inner-most status
          line being displayed

    Note: If a line without a newline is written it will temporarly hide the
          display of the status line until a newline is written

    Examples:
        # ---- as context manager ----
        with status_line('initial status', spint=True) as status:
            # work
            status('updated status line')

            # work
            status('final status line')

        # ---- as object ----
        status = status_line('initial status', dots=True)
        # work
        status('updates status line')
        # work
        status('final status line')

        for i in range(5):
            status() # move the dots w/o changing the status

        status.done(keep = False) # stop the status line from displaying
                                  # clear the status line instead of keeping it
                                  # on the screen

    Attributes:
        status_line (str): The current status line that is being displayed
        clear_line (str): The line used to clear the current status line
        stdout (io.TextWrapper): Reference to the original stdout object
                                 before being replaced with this object
        spin (list[str]): The frames for the spinning circle
        dots (list[str]): The frames for the moving dots
        idx (int): The index into the spin or dots array of the frame to print
        running (bool): If the object has replaced stdout with itself
        displayed (bool): If the status line was displayed or if there was a
                          partial line that was written and is currently displayed
    """

    def __init__(self, initial=None, spin=False, dots=False, print_status=False):
        """
        Args:
            initial (optional[str]): The initial status line to display
            spin (bool): If there should be a spinner prefix to the status line
            dots (bool): If there should be moving dots at the end of the status line
            print_status (bool): If the status line should also be printed when set
        """
        columns = shutil.get_terminal_size().columns

        self.status_line = None
        self.clear_line = '\r' + (' ' * columns) + '\r' # TODO handle screen resize
        self.stdout = None

        self.spin = None
        self.dots =None
        if spin:
            self.spin = ['- ','\\ ', '| ', '/ ']
            self.idx = 0
        if dots:
            self.dots = [' .', ' ..', ' ...', ' ....']
            self.idx = 0

        self.print_status = print_status
        self.running = False
        self.displayed = True # True so that a status line can be set before
                              # printing any other data

        if initial is not None:
            self.__call__(initial)

    def __enter__(self):
        """Context Manager start"""
        return self

    def __exit__(self, type, value, traceback):
        """Context Manager stop
        No error handling is done, only restoring stdout is done
        """
        self.done()
        return None

    def write(self, s):
        """Implementation of sys.stdout.write() that handles moving the status line

        Args:
            s (str): String to be written to stdout
        """
        if not self.running: # If we've not replaced stdout, use that
            return sys.stdout.write(s)
        if not self.stdout.isatty(): # If we are piped or redirected don't display status line
            return self.stdout.write(s)
        if len(s) == 0: # if not data, don't do anything
            return
        
        if self.displayed: # If there is a status line, remove it from the display
            self.stdout.write(self.clear_line)
            self.displayed = False

        self.stdout.write(s) # Write the requested data

        if s[-1] == '\n': # If the last character is a new line then display the status line
            self.write_status()
            self.displayed = True

        self.stdout.flush() # Force the display of partial buffered data

    def write_status(self, advance=True):
        """Common method for displaying the status line with the spinner or dots

        Args:
            advance (bool): If the spinner or dots index counter should be advanced
        """
        # Display the spinner
        if self.spin is not None:
            self.stdout.write(self.spin[self.idx])
            if advance:
                self.idx = (self.idx + 1) % 4

        # Print the status line
        if self.status_line is not None:
            self.stdout.write(self.status_line)

        # Display the dots
        if self.dots is not None:
            self.stdout.write(self.dots[self.idx])
            if advance:
                self.idx = (self.idx + 1) % 4

    def flush(self):
        pass # Prevent an AttributeError

    def isatty(self):
        """If the underlying stdout is a TTY or if it is piped / redirected"""
        try:
            return self.stdout.isatty()
        except AttributeError:
            return False

    def __call__(self, value=None):
        """The status() method that is used to display a new status line or to
        spin the spinner or move the dots

        If no new status line is given then the spinner will spin or the dots will move
        and the current status line will be used

        Args:
            value (optional[str]): The new status line to display
        """
        if not self.running: # ???: just call `start()`?
            self.start() # Delayed initialization so that is being used as an object
                         # that the user doesn't have to remember to call `start()`

        if value is not None:
            self.status_line = value

        if not self.stdout.isatty(): # If piped or redirected, act as a normal print statment
            if value is not None:
                self.stdout.write(self.status_line)
                self.stdout.write('\n')
                self.stdout.flush()
        elif self.print_status:
            print(value) # will also update the displayed status line
        else:
            if self.displayed: # Only display the status line if we are currently displaying one
                self.stdout.write(self.clear_line)
                self.write_status()
                self.stdout.flush()

    def start(self):
        """Replace stdout with ourselves to handle moving the status line"""
        if self.running:
            return

        self.running = True

        # replace stdout
        self.stdout = sys.stdout
        sys.stdout = self

    def done(self, keep=True):
        """Restore stdout and finalize the display

        Args:
            keep (bool): If the status line should be kept as a normal line of output
        """
        if not self.running:
            return

        self.running = False

        if (self.displayed or keep) and self.stdout.isatty():
            if self.displayed:
                self.stdout.write(self.clear_line) # remove spin or dots
            elif not self.displayed:
                self.stdout.write('\n')

            if keep and self.status_line is not None:
                self.stdout.write(self.status_line)
                self.stdout.write('\n') # keep the status line

            self.stdout.flush()

        # restore stdout
        sys.stdout = self.stdout

if __name__ == '__main__':
    # Test of the different functions
    init()

    import time
    with status_line('status line', spin=True) as status:
        red("red fish") ; time.sleep(1)
        blue("blue fish") ; time.sleep(1)
        yellow("one fish") ; time.sleep(1)
        green("two fish") ; time.sleep(1)

        r = confirm('Are you sure?', timeout=None)
        print('Are you sure? {}'.format(r))

    print()
    print("---------------------")
    print()

    status = status_line('status line', dots=True)
    fail('one potato') ; time.sleep(1)
    error('two potato') ; time.sleep(1)
    warning('three potato') ; time.sleep(1)
    info('four potato') ; time.sleep(1)
    debug('five potato') ; time.sleep(1)
    print('six potato') ; time.sleep(1)
    print('more') ; time.sleep(1)
    r = confirm('Are you sure?', timeout=3)
    print('Are you sure? {}'.format(r))
    status.done()

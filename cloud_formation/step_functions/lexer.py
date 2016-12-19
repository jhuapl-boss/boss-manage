
import tokenize
import token

USELESS = ['NEWLINE', 'NL']

class Token(object):
    def __init__(self, code, value, start=(0,0), stop=(0,0), line=''):
        try:
            self.code = token.tok_name[code]
        except:
            self.code = code
        self.value = value
        self.start = start
        self.stop = stop
        self.line = line

    def __str__(self):
        pos = '{},{}-{},{}'.format(*self.start, *self.stop)
        return '{}, {}, {!r}'.format(pos, self.code, self.value)

    def __repr__(self):
        return '{}({!r}, {!r}, {!r}, {!r}, {!r})'.format(self.__class__.__name__,
                                               self.code,
                                               self.value,
                                               self.start,
                                               self.stop,
                                               self.line)

    def __eq__(self, other):
        return (self.code, self.value) == (other.code, other.value)

def tokenize_file(name):
    with open(name, 'r') as fh:
        tokens = tokenize.generate_tokens(fh.readline)
        tokens = [Token(*t) for t in tokens]
        return [t for t in tokens if t.code not in USELESS]


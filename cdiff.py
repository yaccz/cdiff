#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Term based tool to view **colored**, **incremental** diff in *git/svn/hg*
workspace, given patch or two files, or from stdin, with **side by side** and
**auto pager** support.  Requires python (>= 2.5.0) and ``less``.
"""

META_INFO = {
    'version'     : '0.3',
    'license'     : 'BSD-3',
    'author'      : 'Matthew Wang',
    'email'       : 'mattwyl(@)gmail(.)com',
    'url'         : 'https://github.com/ymattw/cdiff',
    'keywords'    : 'colored incremental side-by-side diff',
    'description' : ('View colored, incremental diff in workspace, given patch '
                     'or two files, or from stdin, with side by side and  auto '
                     'pager support')
}

import sys

if sys.hexversion < 0x02050000:
    sys.stderr.write("*** Requires python >= 2.5.0\n")
    sys.exit(1)
IS_PY3 = sys.hexversion >= 0x03000000

import os
import re
import subprocess
import errno
import difflib


COLORS = {
    'reset'         : '\x1b[0m',
    'underline'     : '\x1b[4m',
    'reverse'       : '\x1b[7m',
    'red'           : '\x1b[31m',
    'green'         : '\x1b[32m',
    'yellow'        : '\x1b[33m',
    'blue'          : '\x1b[34m',
    'magenta'       : '\x1b[35m',
    'cyan'          : '\x1b[36m',
    'lightred'      : '\x1b[1;31m',
    'lightgreen'    : '\x1b[1;32m',
    'lightyellow'   : '\x1b[1;33m',
    'lightblue'     : '\x1b[1;34m',
    'lightmagenta'  : '\x1b[1;35m',
    'lightcyan'     : '\x1b[1;36m',
}


# Keys for checking and values for diffing.
REVISION_CONTROL = (
    (['git', 'rev-parse'], ['git', 'diff']),
    (['svn', 'info'], ['svn', 'diff']),
    (['hg', 'summary'], ['hg', 'diff'])
)


def ansi_code(color):
    return COLORS.get(color, '')

def colorize(text, start_color, end_color='reset'):
    return ansi_code(start_color) + text + ansi_code(end_color)


class Hunk(object):

    def __init__(self, hunk_header, old_addr, new_addr):
        self._hunk_header = hunk_header
        self._old_addr = old_addr   # tuple (start, offset)
        self._new_addr = new_addr   # tuple (start, offset)
        self._hunk_list = []        # list of tuple (attr, line)

    def get_header(self):
        return self._hunk_header

    def get_old_addr(self):
        return self._old_addr

    def get_new_addr(self):
        return self._new_addr

    def append(self, attr, line):
        """attr: '-': old, '+': new, ' ': common"""
        self._hunk_list.append((attr, line))

    def mdiff(self):
        r"""The difflib._mdiff() function returns an interator which returns a
        tuple: (from line tuple, to line tuple, boolean flag)

        from/to line tuple -- (line num, line text)
            line num -- integer or None (to indicate a context separation)
            line text -- original line text with following markers inserted:
                '\0+' -- marks start of added text
                '\0-' -- marks start of deleted text
                '\0^' -- marks start of changed text
                '\1' -- marks end of added/deleted/changed text

        boolean flag -- None indicates context separation, True indicates
            either "from" or "to" line contains a change, otherwise False.
        """
        return difflib._mdiff(self._get_old_text(), self._get_new_text())

    def _get_old_text(self):
        out = []
        for (attr, line) in self._hunk_list:
            if attr != '+':
                out.append(line)
        return out

    def _get_new_text(self):
        out = []
        for (attr, line) in self._hunk_list:
            if attr != '-':
                out.append(line)
        return out

    def __iter__(self):
        for hunk_line in self._hunk_list:
            yield hunk_line


class Diff(object):

    def __init__(self, headers, old_path, new_path, hunks):
        self._headers = headers
        self._old_path = old_path
        self._new_path = new_path
        self._hunks = hunks

    # Follow detector and the parse_hunk_header() are suppose to be overwritten
    # by derived class
    #
    def is_old_path(self, line):
        return False

    def is_new_path(self, line):
        return False

    def is_hunk_header(self, line):
        return False

    def parse_hunk_header(self, line):
        """Returns a 2-eliment tuple, each of them is a tuple in form of (start,
        offset)"""
        return False

    def is_old(self, line):
        return False

    def is_new(self, line):
        return False

    def is_common(self, line):
        return False

    def is_eof(self, line):
        return False

    def is_header(self, line):
        return False

    def markup_traditional(self):
        """Returns a generator"""
        for line in self._headers:
            yield self._markup_header(line)

        yield self._markup_old_path(self._old_path)
        yield self._markup_new_path(self._new_path)

        for hunk in self._hunks:
            yield self._markup_hunk_header(hunk.get_header())
            for old, new, changed in hunk.mdiff():
                if changed:
                    if not old[0]:
                        # The '+' char after \x00 is kept
                        # DEBUG: yield 'NEW: %s %s\n' % (old, new)
                        line = new[1].strip('\x00\x01')
                        yield self._markup_new(line)
                    elif not new[0]:
                        # The '-' char after \x00 is kept
                        # DEBUG: yield 'OLD: %s %s\n' % (old, new)
                        line = old[1].strip('\x00\x01')
                        yield self._markup_old(line)
                    else:
                        # DEBUG: yield 'CHG: %s %s\n' % (old, new)
                        yield self._markup_old('-') + \
                            self._markup_old_mix(old[1])
                        yield self._markup_new('+') + \
                            self._markup_new_mix(new[1])
                else:
                    yield self._markup_common(' ' + old[1])

    def markup_side_by_side(self, width):
        """Returns a generator"""
        def _normalize(line):
            return line.replace('\t', ' '*8).replace('\n', '').replace('\r', '')

        def _fit_width(markup, width, pad=False):
            """str len does not count correctly if left column contains ansi
            color code.  Only left side need to set `pad`
            """
            out = []
            count = 0
            ansi_color_regex = r'\x1b\[(1;)?\d{1,2}m'
            patt = re.compile('^(%s)(.*)' % ansi_color_regex)
            repl = re.compile(ansi_color_regex)

            while markup and count < width:
                if patt.match(markup):
                    out.append(patt.sub(r'\1', markup))
                    markup = patt.sub(r'\3', markup)
                else:
                    # FIXME: utf-8 wchar might break the rule here, e.g.
                    # u'\u554a' takes double width of a single letter, also this
                    # depends on your terminal font.  I guess audience of this
                    # tool never put that kind of symbol in their code :-)
                    #
                    out.append(markup[0])
                    count += 1
                    markup = markup[1:]

            if count == width and repl.sub('', markup):
                # stripped: output fulfil and still have ascii in markup
                out[-1] = ansi_code('reset') + colorize('>', 'lightmagenta')
            elif count < width and pad:
                pad_len = width - count
                out.append('%*s' % (pad_len, ''))

            return ''.join(out)

        # Setup line width and number width
        if width <= 0:
            width = 80
        (start, offset) = self._hunks[-1].get_old_addr()
        max1 = start + offset - 1
        (start, offset) = self._hunks[-1].get_new_addr()
        max2 = start + offset - 1
        num_width = max(len(str(max1)), len(str(max2)))
        left_num_fmt = colorize('%%(left_num)%ds' % num_width, 'yellow')
        right_num_fmt = colorize('%%(right_num)%ds' % num_width, 'yellow')
        line_fmt = left_num_fmt + ' %(left)s ' + ansi_code('reset') + \
                right_num_fmt + ' %(right)s\n'

        # yield header, old path and new path
        for line in self._headers:
            yield self._markup_header(line)
        yield self._markup_old_path(self._old_path)
        yield self._markup_new_path(self._new_path)

        # yield hunks
        for hunk in self._hunks:
            yield self._markup_hunk_header(hunk.get_header())
            for old, new, changed in hunk.mdiff():
                if old[0]:
                    left_num = str(hunk.get_old_addr()[0] + int(old[0]) - 1)
                else:
                    left_num = ' '

                if new[0]:
                    right_num = str(hunk.get_new_addr()[0] + int(new[0]) - 1)
                else:
                    right_num = ' '

                left = _normalize(old[1])
                right = _normalize(new[1])

                if changed:
                    if not old[0]:
                        left = '%*s' % (width, ' ')
                        right = right.lstrip('\x00+').rstrip('\x01')
                        right = _fit_width(self._markup_new(right), width)
                    elif not new[0]:
                        left = left.lstrip('\x00-').rstrip('\x01')
                        left = _fit_width(self._markup_old(left), width)
                        right = ''
                    else:
                        left = _fit_width(self._markup_old_mix(left), width, 1)
                        right = _fit_width(self._markup_new_mix(right), width)
                else:
                    left = _fit_width(self._markup_common(left), width, 1)
                    right = _fit_width(self._markup_common(right), width)
                yield line_fmt % {
                    'left_num': left_num,
                    'left': left,
                    'right_num': right_num,
                    'right': right
                }

    def _markup_header(self, line):
        return colorize(line, 'cyan')

    def _markup_old_path(self, line):
        return colorize(line, 'yellow')

    def _markup_new_path(self, line):
        return colorize(line, 'yellow')

    def _markup_hunk_header(self, line):
        return colorize(line, 'lightblue')

    def _markup_common(self, line):
        return colorize(line, 'reset')

    def _markup_old(self, line):
        return colorize(line, 'lightred')

    def _markup_new(self, line):
        return colorize(line, 'lightgreen')

    def _markup_mix(self, line, base_color):
        del_code = ansi_code('reverse') + ansi_code(base_color)
        add_code = ansi_code('reverse') + ansi_code(base_color)
        chg_code = ansi_code('underline') + ansi_code(base_color)
        rst_code = ansi_code('reset') + ansi_code(base_color)
        line = line.replace('\x00-', del_code)
        line = line.replace('\x00+', add_code)
        line = line.replace('\x00^', chg_code)
        line = line.replace('\x01', rst_code)
        return colorize(line, base_color)

    def _markup_old_mix(self, line):
        return self._markup_mix(line, 'red')

    def _markup_new_mix(self, line):
        return self._markup_mix(line, 'green')


class Udiff(Diff):

    def is_old_path(self, line):
        return line.startswith('--- ')

    def is_new_path(self, line):
        return line.startswith('+++ ')

    def is_hunk_header(self, line):
        return line.startswith('@@ -')

    def parse_hunk_header(self, hunk_header):
        # @@ -3,7 +3,6 @@
        a = hunk_header.split()[1].split(',')   # -3 7
        if len(a) > 1:
            old_addr = (int(a[0][1:]), int(a[1]))
        else:
            # @@ -1 +1,2 @@
            old_addr = (int(a[0][1:]), 0)

        b = hunk_header.split()[2].split(',')   # +3 6
        if len(b) > 1:
            new_addr = (int(b[0][1:]), int(b[1]))
        else:
            # @@ -0,0 +1 @@
            new_addr = (int(b[0][1:]), 0)

        return (old_addr, new_addr)

    def is_old(self, line):
        return line.startswith('-') and not self.is_old_path(line)

    def is_new(self, line):
        return line.startswith('+') and not self.is_new_path(line)

    def is_common(self, line):
        return line.startswith(' ')

    def is_eof(self, line):
        # \ No newline at end of file
        return line.startswith('\\')

    def is_header(self, line):
        return re.match(r'^[^+@\\ -]', line)


class DiffParser(object):

    def __init__(self, stream):
        """Detect Udiff with 3 conditions"""
        flag = 0
        for line in stream[:20]:
            if line.startswith('--- '):
                flag |= 1
            elif line.startswith('+++ '):
                flag |= 2
            elif line.startswith('@@ '):
                flag |= 4
        if flag & 7:
            self._type = 'udiff'
        else:
            raise RuntimeError('unknown diff type')

        try:
            self._diffs = self._parse(stream)
        except (AssertionError, IndexError):
            raise RuntimeError('invalid patch format')

    def get_diffs(self):
        return self._diffs

    def _parse(self, stream):
        """parse all diff lines, construct a list of Diff objects"""
        if self._type == 'udiff':
            difflet = Udiff(None, None, None, None)
        else:
            raise RuntimeError('unsupported diff format')

        out_diffs = []
        headers = []
        old_path = None
        new_path = None
        hunks = []
        hunk = None

        while stream:
            # 'common' line occurs before 'old_path' is considered as header
            # too, this happens with `git log -p` and `git show <commit>`
            #
            if difflet.is_header(stream[0]) or \
                    (difflet.is_common(stream[0]) and old_path is None):
                if headers and old_path:
                    # Encounter a new header
                    assert new_path is not None
                    assert hunk is not None
                    hunks.append(hunk)
                    out_diffs.append(Diff(headers, old_path, new_path, hunks))
                    headers = []
                    old_path = None
                    new_path = None
                    hunks = []
                    hunk = None
                else:
                    headers.append(stream.pop(0))

            elif difflet.is_old_path(stream[0]):
                if old_path:
                    # Encounter a new patch set
                    assert new_path is not None
                    assert hunk is not None
                    hunks.append(hunk)
                    out_diffs.append(Diff(headers, old_path, new_path, hunks))
                    headers = []
                    old_path = None
                    new_path = None
                    hunks = []
                    hunk = None
                else:
                    old_path = stream.pop(0)

            elif difflet.is_new_path(stream[0]):
                assert old_path is not None
                assert new_path is None
                new_path = stream.pop(0)

            elif difflet.is_hunk_header(stream[0]):
                assert old_path is not None
                assert new_path is not None
                if hunk:
                    # Encounter a new hunk header
                    hunks.append(hunk)
                    hunk = None
                else:
                    hunk_header = stream.pop(0)
                    old_addr, new_addr = difflet.parse_hunk_header(hunk_header)
                    hunk = Hunk(hunk_header, old_addr, new_addr)

            elif difflet.is_old(stream[0]) or difflet.is_new(stream[0]) or \
                    difflet.is_common(stream[0]):
                assert old_path is not None
                assert new_path is not None
                assert hunk is not None
                hunk_line = stream.pop(0)
                hunk.append(hunk_line[0], hunk_line[1:])

            elif difflet.is_eof(stream[0]):
                # ignore
                stream.pop(0)

            else:
                raise RuntimeError('unknown patch format: %s' % stream[0])

        # The last patch
        if hunk:
            hunks.append(hunk)
        if old_path:
            if new_path:
                out_diffs.append(Diff(headers, old_path, new_path, hunks))
            else:
                raise RuntimeError('unknown patch format after "%s"' % old_path)
        elif headers:
            raise RuntimeError('unknown patch format: %s' % \
                    ('\n'.join(headers)))

        return out_diffs


class DiffMarkup(object):

    def __init__(self, stream):
        self._diffs = DiffParser(stream).get_diffs()

    def markup(self, side_by_side=False, width=0):
        """Returns a generator"""
        if side_by_side:
            return self._markup_side_by_side(width)
        else:
            return self._markup_traditional()

    def _markup_traditional(self):
        for diff in self._diffs:
            for line in diff.markup_traditional():
                yield line

    def _markup_side_by_side(self, width):
        for diff in self._diffs:
            for line in diff.markup_side_by_side(width):
                yield line


def markup_to_pager(stream, opts):
    markup = DiffMarkup(stream)
    color_diff = markup.markup(side_by_side=opts.side_by_side,
            width=opts.width)

    # args stolen fron git source: github.com/git/git/blob/master/pager.c
    pager = subprocess.Popen(['less', '-FRSXK'],
            stdin=subprocess.PIPE, stdout=sys.stdout)
    for line in color_diff:
        pager.stdin.write(line.encode('utf-8'))

    pager.stdin.close()
    pager.wait()


def check_command_status(arguments):
    """Return True if command returns 0."""
    try:
        return subprocess.call(
            arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE) == 0
    except OSError:
        return False


def revision_control_diff():
    """Return diff from revision control system."""
    for check, diff in REVISION_CONTROL:
        if check_command_status(check):
            return subprocess.Popen(diff, stdout=subprocess.PIPE).stdout


def decode(line):
    """Decode UTF-8 if necessary."""
    try:
        return line.decode('utf-8')
    except AttributeError:
        return line


def main():
    import optparse

    supported_vcs = [check[0] for check, _ in REVISION_CONTROL]

    usage = """
  %prog [options]
  %prog [options] <patch>
  %prog [options] <file1> <file2>"""
    parser = optparse.OptionParser(usage=usage,
            description=META_INFO['description'],
            version='%%prog %s' % META_INFO['version'])
    parser.add_option('-s', '--side-by-side', action='store_true',
            help=('show in side-by-side mode'))
    parser.add_option('-w', '--width', type='int', default=80, metavar='N',
            help='set text width (side-by-side mode only), default is 80')
    opts, args = parser.parse_args()

    if len(args) > 2:
        parser.print_help()
        return 1
    elif len(args) == 2:
        diff_hdl = subprocess.Popen(['diff', '-u', args[0], args[1]],
                stdout=subprocess.PIPE).stdout
    elif len(args) == 1:
        if IS_PY3:
            # Python3 needs the newline='' to keep '\r' (DOS format)
            diff_hdl = open(args[0], mode='rt', newline='')
        else:
            diff_hdl = open(args[0], mode='rt')
    elif sys.stdin.isatty():
        diff_hdl = revision_control_diff()
        if not diff_hdl:
            sys.stderr.write(('*** Not in a supported workspace, supported '
                              'are: %s\n\n') % ', '.join(supported_vcs))
            parser.print_help()
            return 1
    else:
        diff_hdl = sys.stdin

    # FIXME: can't use generator for now due to current implementation in parser
    stream = [decode(line) for line in diff_hdl.readlines()]

    if diff_hdl is not sys.stdin:
        diff_hdl.close()

    # Don't let empty diff pass thru
    if not stream:
        return 0

    if sys.stdout.isatty():
        try:
            markup_to_pager(stream, opts)
        except IOError:
            e = sys.exc_info()[1]
            if e.errno == errno.EPIPE:
                pass
    else:
        # pipe out stream untouched to make sure it is still a patch
        sys.stdout.write(''.join(stream))

    return 0


if __name__ == '__main__':
    sys.exit(main())

# vim:set et sts=4 sw=4 tw=80:

Cdiff
=====

Term based tool to view **colored**, **incremental** diff in *git/svn/hg*
workspace, given patch or two files, or from stdin, with **side by side** and
**auto pager** support.  Requires python (>= 2.5.0) and ``less``.

.. image:: http://ymattw.github.com/cdiff/img/default.png
   :alt: default
   :align: center

.. image:: http://ymattw.github.com/cdiff/img/side-by-side.png
   :alt: side by side
   :align: center
   :width: 900 px

Installation
------------

Install with pip
~~~~~~~~~~~~~~~~

Cdiff is already listed on `PyPI <http://pypi.python.org/pypi/cdiff>`_, you can
install with ``pip`` if you have the tool.

.. code:: sh
 
    sudo pip install cdiff

Install with setup.py
~~~~~~~~~~~~~~~~~~~~~

You can also run the setup.py from the source if you don't have ``pip``.

.. code:: sh

    git clone https://github.com/ymattw/cdiff.git
    cd cdiff
    sudo ./setup.py install

Download directly
~~~~~~~~~~~~~~~~~

Both ``pip`` and ``setup.py`` installs cdiff to system wide directory, if you
want a minimal tool without the boring external dependencies (like me), just
save `cdiff.py <https://raw.github.com/ymattw/cdiff/master/cdiff.py>`_ to
whatever directory which is in your ``$PATH``, for example, ``$HOME/bin`` is in
my ``$PATH``, so I save the script there and name as ``cdiff``.

.. code:: sh

    curl -ksS https://raw.github.com/ymattw/cdiff/master/cdiff.py > ~/bin/cdiff
    chmod +x ~/bin/cdiff

Usage
-----

Cdiff reads diff from diff (patch) file if given, or stdin if redirected, or
diff produced by revision tool if in a git/svn/hg workspace.  Use option ``-s``
to enable side by side view, and option ``-w N`` to set a text width other than
default ``80``.  See examples below.

Show usage::

    cdiff -h

Read diff from local modification in a svn, git, or hg workspace:

.. code:: sh

    cd proj-workspace
    cdiff                   # view colored incremental udiff
    cdiff -s                # view side by side
    cdiff -s -w 90          # use text width 90 other than default 80

Pipe in a diff:

.. code:: sh

    git log -p -2 | cdiff -s
    git show 15bfa5 | cdiff -s
    svn diff -r PREV | cdiff -s

View a diff (patch) file:

.. code:: sh

    cdiff foo.patch
    cdiff foo.patch -s
    cdiff foo.patch -s -w 90

View diff between two files (wrapper of ``diff``)::

    cdiff foo foo.new       # equivalent to diff -u foo foo.new | cdiff
    cdiff foo foo.new -s

Redirect output to another patch file is safe:

.. code:: sh

    svn diff | cdiff -s > my.patch

Notes
-----

- Works with python >= 2.5.0 (subprocess.Popen seems not working with PIPE in
  2.4.3, maybe you can fix it)
- Only takes unified diff for input
- Side by side mode has alignment problem for wide chars

Pull request is very welcome, make sure run ``make test`` to verify.  It only
has minimal verification today and that depends on human eyes too (`issue #7
<https://github.com/ymattw/cdiff/issues/7>`_).  Single commit in pull request
would make it easier for review, for example to collapse last 3 commits into 1
before *push*, use ``git rebase -i HEAD~3``, *pick* the first and *squash* the
other two.

See also
--------

I have another tool `coderev <https://github.com/ymattw/coderev>`_ which
generates side-by-side diff pages for code review from two given files or
directories, I found it's not easy to extend to support git so invented
`cdiff`.  Idea of ansi color markup is also from project `colordiff
<https://github.com/daveewart/colordiff>`_.


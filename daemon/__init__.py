# -*- coding: utf-8 -*-

# daemon/__init__.py
# Part of python-daemon, an implementation of PEP 3143.
#
# Copyright © 2014 Alex Honeywell
# Copyright © 2009–2010 Ben Finney <ben+python@benfinney.id.au>
# Copyright © 2006 Robert Niederreiter
#
# This is free software: you may copy, modify, and/or distribute this work
# under the terms of the Python Software Foundation License, version 2 or
# later as published by the Python Software Foundation.
# No warranty expressed or implied. See the file LICENSE.PSF-2 for details.
""" Library to implement a well-behaved Unix daemon process.

    This library implements the well-behaved daemon specification of
    :pep:`3143`, "Standard daemon process library".

    A well-behaved Unix daemon process is tricky to get right, but the
    required steps are much the same for every daemon program. A
    `DaemonContext` instance holds the behaviour and configured
    process environment for the program; use the instance as a context
    manager to enter a daemon state.

    Example of spawn-and-exit usage::

        import daemon

        from spam import do_main_program

        with daemon.DaemonContext():
            do_main_program()

    Customisation of the steps to become a daemon is available by
    setting options on the `DaemonContext` instance; see the
    documentation for that class for each option.

    Example of spawn-and-continue usage::

        import daemon

        from spam import do_main_program, do_other_stuff

        # Spawned in daemon process
        daemon.create_daemon(do_main_program).start()

        # Continue execution of current process
        do_other_stuff()
"""

from __future__ import unicode_literals, print_function, absolute_import

from types import MethodType

from .daemon import DaemonContext


VERSION = '2.1'
LICENSE = 'PSF-2+'
URL = 'https://github.com/asoc/python-daemon'

AUTHOR = 'Alex Honeywell'
AUTHOR_EMAIL = 'alex.honeywell@gmail.com'


def create_daemon(run, *args, **kwargs):
    """ Create a DaemonRunner with the given run method. """
    if not callable(run):
        raise TypeError('Argument `run` must be callable.')

    from .runner import DaemonRunner

    d = DaemonRunner(*args, **kwargs)
    d.run = MethodType(run, d)
    return d

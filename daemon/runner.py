# -*- coding: utf-8 -*-

# daemon/runner.py
# Part of python-daemon, an implementation of PEP 3143.
#
# Copyright © 2014 Alex Honeywell
# Copyright © 2009–2010 Ben Finney <ben+python@benfinney.id.au>
# Copyright © 2007–2008 Robert Niederreiter, Jens Klein
# Copyright © 2003 Clark Evans
# Copyright © 2002 Noah Spurrier
# Copyright © 2001 Jürgen Hermann
#
# This is free software: you may copy, modify, and/or distribute this work
# under the terms of the Python Software Foundation License, version 2 or
# later as published by the Python Software Foundation.
# No warranty expressed or implied. See the file LICENSE.PSF-2 for details.
""" Daemon runner library. """

from __future__ import unicode_literals, print_function, absolute_import

import errno
import os
import signal
import six
import sys

from . import pidlockfile, DaemonContext


class DaemonRunnerError(Exception):
    """ Abstract base class for errors from DaemonRunner. """


class DaemonRunnerInvalidActionError(ValueError, DaemonRunnerError):
    """ Raised when specified action for DaemonRunner is invalid. """


class DaemonRunnerStartFailureError(RuntimeError, DaemonRunnerError):
    """ Raised when failure starting DaemonRunner. """


class DaemonRunnerStopFailureError(RuntimeError, DaemonRunnerError):
    """ Raised when failure stopping DaemonRunner. """


class _FakeSTDIN(object):
    def read(self):
        raise EOFError()

    def readline(self):
        raise EOFError()

    def fileno(self):
        return sys.stdin.fileno()


class DaemonRunner(object):
    """ Controller for a callable running in a separate background process.

        The first command-line argument is the action to take:

        * 'start': Become a daemon and call `app.run()`.
        * 'stop': Exit the daemon process specified in the PID file.
        * 'restart': Stop, then start.
    """

    def __init__(self, stdout=None, stderr=None, stdin=None, pidfile=None, pidfile_timeout=None):
        """ Set up the parameters of a new runner.

            * `stdin`, `stdout`, `stderr`: Filesystem
              paths to open and replace the existing `sys.stdin`,
              `sys.stdout`, `sys.stderr`.

              If `stdout` or `stderr` are `None`, then will write to `os.devnull`
              If `stdin` is `None`, a `_FakeSTDIN` instance will be used

            * `pidfile`: Absolute filesystem path to a file that
              will be used as the PID file for the daemon. If
              ``None``, no PID file will be used.

            * `pidfile_timeout`: Used as the default acquisition
              timeout value supplied to the runner's PID lock file.
        """
        self.daemon_context = DaemonContext()
        self.daemon_context.stdin = open(stdin, 'r') if stdin else sys.stdin
        self.daemon_context.stdout = open(stdout if stdout else os.devnull, 'w+')
        self.daemon_context.stderr = open(stderr if stderr else os.devnull, 'w+')

        self.pidfile = None
        if pidfile:
            self.pidfile = make_pidlockfile(pidfile, pidfile_timeout)
        self.daemon_context.pidfile = self.pidfile

    def run(self):
        pass

    def start(self):
        """ Open the daemon context and run the application. """
        if is_pidfile_stale(self.pidfile):
            self.pidfile.break_lock()

        try:
            self.daemon_context.open()
        except pidlockfile.AlreadyLocked:
            raise DaemonRunnerStartFailureError('PID file {} already locked'.format(self.pidfile.path))
        except SystemExit:
            return

        sys.exit(self.run())

    def __terminate_daemon_process(self):
        """ Terminate the daemon process specified in the current PID file. """
        if not self.pidfile:
            return

        pid = self.pidfile.read_pid()
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as exc:
            raise DaemonRunnerStopFailureError('Failed to terminate {:d}: {!s}'.format(pid, exc))

    def stop(self):
        """ Exit the daemon process specified in the current PID file. """
        if not self.pidfile:
            raise DaemonRunnerStopFailureError('Cannot stop daemon with no PID file')

        if not self.pidfile.is_locked():
            raise DaemonRunnerStopFailureError('PID file {} not locked'.format(self.pidfile.path))

        if is_pidfile_stale(self.pidfile):
            self.pidfile.break_lock()
        else:
            self.__terminate_daemon_process()

    def restart(self):
        """ Stop, then start. """
        self.stop()
        self.start()


def make_pidlockfile(path, acquire_timeout):
    """ Make a PIDLockFile instance with the given filesystem path. """
    if not isinstance(path, six.string_types):
        raise ValueError('Not a filesystem path: {}'.format(path))

    if not os.path.isabs(path):
        raise ValueError('Not an absolute path: {}'.format(path))

    return pidlockfile.TimeoutPIDLockFile(path, acquire_timeout)


def is_pidfile_stale(pidfile):
    """ Determine whether a PID file is stale.

        Return ``True`` (“stale”) if the contents of the PID file are
        valid but do not match the PID of a currently-running process;
        otherwise return ``False``.
    """
    if not pidfile:
        return False

    pidfile_pid = pidfile.read_pid()
    if pidfile_pid is not None:
        try:
            os.kill(pidfile_pid, signal.SIG_DFL)
        except OSError as exc:
            if exc.errno == errno.ESRCH:
                # The specified PID does not exist
                return True

    return False

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
import time


from . import pidlockfile, DaemonContext


class DaemonRunnerError(Exception):
    """ Abstract base class for errors from DaemonRunner. """


class DaemonRunnerInvalidActionError(ValueError, DaemonRunnerError):
    """ Raised when specified action for DaemonRunner is invalid. """


class DaemonRunnerStartFailureError(RuntimeError, DaemonRunnerError):
    """ Raised when failure starting DaemonRunner. """


class DaemonRunnerStopFailureError(RuntimeError, DaemonRunnerError):
    """ Raised when failure stopping DaemonRunner. """


class DaemonRunner(object):
    """ Controller for a callable running in a separate background process.

        The first command-line argument is the action to take:

        * 'start': Become a daemon and call `app.run()`.
        * 'stop': Exit the daemon process specified in the PID file.
        * 'restart': Stop, then start.
    """

    def __init__(self, stdout=None, stderr=None, stdin=None, pidfile=None, pidfile_timeout=None, manage_pidfile=True, context_kwargs=None):
        """ Set up the parameters of a new runner.

            * `stdin`, `stdout`, `stderr`: Filesystem
              paths to open and replace the existing `sys.stdin`,
              `sys.stdout`, `sys.stderr`.

              If `stdout` or `stderr` are `None`, then will write to `os.devnull`
              If they are `file` objects those will be used
                 (only recommended for direct `run()` calls)
              If `stdin` is `None`, `sys.stdin` will be used.

            * `pidfile`: Absolute filesystem path to a file that
              will be used as the PID file for the daemon. If
              ``None``, no PID file will be used.

            * `pidfile_timeout`: Used as the default acquisition
              timeout value supplied to the runner's PID lock file.
        """
        self.daemon_context = DaemonContext(**context_kwargs or {})

        self.__set_std('stdin', stdin, os.devnull, 'r')
        self.__set_std('stdout', stdout, os.devnull, 'w+')
        if stdout == stderr:
            self.__set_std('stderr', self.stdout, os.devnull, 'w+')
        else:
            self.__set_std('stderr', stderr, os.devnull, 'w+')

        self.pidfile = pidfile
        self.manage_pidfile = manage_pidfile

        if pidfile and manage_pidfile:
            self.pidfile = make_pidlockfile(pidfile, pidfile_timeout)

        self.daemon_context.pidfile = self.pidfile
        self.daemon_context.manage_pidfile = self.manage_pidfile

    def __set_std(self, name, value, default, mode):
        def get_default():
            if default and not hasattr(default, 'read'):
                return open(default, mode)
            return default

        if value is None or hasattr(value, 'read'):
            setattr(self.daemon_context, name, value or get_default())
            return

        setattr(
            self.daemon_context, name,
            open(value, mode) if isinstance(value, six.string_types) and value else get_default()
        )

    def __getattr__(self, item):
            return getattr(self.daemon_context, item)

    def run(self):
        pass

    def start(self, delay_after_fork=None):
        """ Open the daemon context and run the application. """
        if self.manage_pidfile and is_pidfile_stale(self.pidfile):
            self.pidfile.break_lock()

        try:
            with self.daemon_context:
                if delay_after_fork:
                    time.sleep(delay_after_fork)
                try:
                    os._exit(self.run() or 0)
                except SystemExit as err:
                    code = err.code or 0
                    if isinstance(code, six.string_types):
                        code = 1
                    os._exit(code)
        except pidlockfile.AlreadyLocked:
            raise DaemonRunnerStartFailureError('PID file {} already locked'.format(self.pidfile.path))
        except SystemExit:
            pass

    def __terminate_daemon_process(self):
        """ Terminate the daemon process specified in the current PID file. """
        if not self.pidfile:
            return

        pid = self.pid

        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as exc:
            raise DaemonRunnerStopFailureError('Failed to terminate {:d}: {!s}'.format(pid, exc))

    def stop(self):
        """ Exit the daemon process specified in the current PID file. """
        if not self.pidfile:
            raise DaemonRunnerStopFailureError('Cannot stop daemon with no PID file')

        if not self.alive:
            return

        if not self.manage_pidfile:
            self.__terminate_daemon_process()
            return

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

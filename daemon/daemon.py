# -*- coding: utf-8 -*-

# daemon/daemon.py
# Part of python-daemon, an implementation of PEP 3143.
#
# Copyright 2014-2016 Alex Honeywell
# Copyright 2008–2010 Ben Finney <ben+python@benfinney.id.au>
# Copyright 2007–2008 Robert Niederreiter, Jens Klein
# Copyright 2004–2005 Chad J. Schroeder
# Copyright 2003 Clark Evans
# Copyright 2002 Noah Spurrier
# Copyright 2001 Jürgen Hermann
#
# This is free software: you may copy, modify, and/or distribute this work
# under the terms of the Python Software Foundation License, version 2 or
# later as published by the Python Software Foundation.
# No warranty expressed or implied. See the file LICENSE.PSF-2 for details.
""" Daemon process behaviour. """

from __future__ import unicode_literals, print_function, absolute_import

import atexit
import errno
import os
import resource
import signal
import six
import socket
import sys

from setproctitle import setproctitle

from six.moves import StringIO


_default_std_info = {
    'w+': {
        'attr': 'write',
        'buffering': -1,
    },
    'wb+': {
        'attr': 'write',
        'buffering': 0,
    },
    'r': {
        'attr': 'read',
        'buffering': -1,
    },
}


class DaemonError(Exception):
    """ Base exception class for errors from this module. """


class DaemonOSEnvironmentError(DaemonError, OSError):
    """ Exception raised when daemon OS environment setup receives error. """


class DaemonProcessDetachError(DaemonError, OSError):
    """ Exception raised when process detach fails. """


class DaemonContext(object):
    """ Context for turning the current program into a daemon process.

        Using a `DaemonContext` directly will terminate the calling process.
        Use a `DaemonRunner` or `daemon.create_daemon(...)` to spawn a daemon
        and continue execution.

        A `DaemonContext` instance represents the behaviour settings and
        process context for the program when it becomes a daemon. The
        behaviour and environment is customised by setting options on the
        instance, before calling the `open` method.

        Each option can be passed as a keyword argument to the `DaemonContext`
        constructor, or subsequently altered by assigning to an attribute on
        the instance at any time prior to calling `open`. That is, for
        options named `wibble` and `wubble`, the following invocation::

            foo = daemon.DaemonContext(wibble=bar, wubble=baz)
            foo.open()

        is equivalent to::

            foo = daemon.DaemonContext()
            foo.wibble = bar
            foo.wubble = baz
            foo.open()

        The following options are defined.

        `files_preserve`
            :Default: ``None``

            List of files that should *not* be closed when starting the
            daemon. If ``None``, all open file descriptors will be closed.

            Elements of the list are file descriptors (as returned by a file
            object's `fileno()` method) or Python `file` objects. Each
            specifies a file that is not to be closed during daemon start.

        `chroot_directory`
            :Default: ``None``

            Full path to a directory to set as the effective root directory of
            the process. If ``None``, specifies that the root directory is not
            to be changed.

        `working_directory`
            :Default: ``'/'``

            Full path of the working directory to which the process should
            change on daemon start.

            Since a filesystem cannot be unmounted if a process has its
            current working directory on that filesystem, this should either
            be left at default or set to a directory that is a sensible “home
            directory” for the daemon while it is running.

        `umask`
            :Default: ``0``

            File access creation mask (“umask”) to set for the process on
            daemon start.

            Since a process inherits its umask from its parent process,
            starting the daemon will reset the umask to this value so that
            files are created by the daemon with access modes as it expects.

        `pidfile`
            :Default: ``None``

            Context manager for a PID lock file. When the daemon context opens
            and closes, it enters and exits the `pidfile` context manager.

        `detach_process`
            :Default: ``None``

            If ``True``, detach the process context when opening the daemon
            context; if ``False``, do not detach.

            If unspecified (``None``) during initialisation of the instance,
            this will be set to ``True`` by default, and ``False`` only if
            detaching the process is determined to be redundant; for example,
            in the case when the process was started by `init`, by `initd`, or
            by `inetd`.

        `signal_map`
            :Default: system-dependent

            Mapping from operating system signals to callback actions.

            The mapping is used when the daemon context opens, and determines
            the action for each signal's signal handler:

            * A value of ``None`` will ignore the signal (by setting the
              signal action to ``signal.SIG_IGN``).

            * A string value will be used as the name of an attribute on the
              ``DaemonContext`` instance. The attribute's value will be used
              as the action for the signal handler.

            * Any other value will be used as the action for the
              signal handler. See the ``signal.signal`` documentation
              for details of the signal handler interface.

            The default value depends on which signals are defined on the
            running system. Each item from the list below whose signal is
            actually defined in the ``signal`` module will appear in the
            default map:

            * ``signal.SIGTTIN``: ``None``

            * ``signal.SIGTTOU``: ``None``

            * ``signal.SIGTSTP``: ``None``

            * ``signal.SIGTERM``: ``'terminate'``

            Depending on how the program will interact with its child
            processes, it may need to specify a signal map that
            includes the ``signal.SIGCHLD`` signal (received when a
            child process exits). See the specific operating system's
            documentation for more detail on how to determine what
            circumstances dictate the need for signal handlers.

        `uid`
            :Default: ``os.getuid()``

        `gid`
            :Default: ``os.getgid()``

            The user ID (“UID”) value and group ID (“GID”) value to switch
            the process to on daemon start.

            The default values, the real UID and GID of the process, will
            relinquish any effective privilege elevation inherited by the
            process.

        `prevent_core`
            :Default: ``True``

            If true, prevents the generation of core files, in order to avoid
            leaking sensitive information from daemons run as `root`.

        `stdin`
            :Default: ``None``

        `stdout`
            :Default: ``None``

        `stderr`
            :Default: ``None``

            Each of `stdin`, `stdout`, and `stderr` is a file-like object
            which will be used as the new file for the standard I/O stream
            `sys.stdin`, `sys.stdout`, and `sys.stderr` respectively. The file
            should therefore be open, with a minimum of mode 'r' in the case
            of `stdin`, and mode 'w+' in the case of `stdout` and `stderr`.

            If the object has a `fileno()` method that returns a file
            descriptor, the corresponding file will be excluded from being
            closed during daemon start (that is, it will be treated as though
            it were listed in `files_preserve`).

            If ``None``, the corresponding system stream is re-bound to the
            file named by `os.devnull`.

        `process_name`
            :Default: ``None``

            If specified, sets the daemonized process's name (ie. what appears
            in `ps`)
        """

    def __init__(self, chroot_directory=None, working_directory='/', umask=0,
                 uid=None, gid=None, prevent_core=True, detach_process=None,
                 files_preserve=None, pidfile=None, manage_pidfile=True,
                 stdin=None, stdout=None, stderr=None, signal_map=None,
                 process_name=None, binary_out=True, binary_err=True):
        """ Set up a new instance. """
        self.chroot_directory = chroot_directory
        self.working_directory = working_directory
        self.umask = umask
        self.prevent_core = prevent_core
        self.files_preserve = files_preserve or []
        self.pidfile = pidfile
        self.manage_pidfile = manage_pidfile
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.process_name = process_name
        self.binary_out = binary_out
        self.binary_err = binary_err

        if uid is None:
            uid = os.getuid()
        self.uid = uid
        if gid is None:
            gid = os.getgid()
        self.gid = gid

        if detach_process is None:
            detach_process = is_detach_process_context_required()
        self.detach_process = detach_process

        if signal_map is None:
            signal_map = make_default_signal_map()
        self.signal_map = signal_map

        self._is_open = False

    @property
    def is_open(self):
        """ ``True`` if the instance is currently open. """
        return self._is_open

    def open(self):
        """ Become a daemon process.
            :Return: ``None``

            Open the daemon context, turning the current program into a daemon
            process. This performs the following steps:

            * If this instance's `is_open` property is true, return
              immediately. This makes it safe to call `open` multiple times on
              an instance.

            * If the `prevent_core` attribute is true, set the resource limits
              for the process to prevent any core dump from the process.

            * If the `chroot_directory` attribute is not ``None``, set the
              effective root directory of the process to that directory (via
              `os.chroot`).

              This allows running the daemon process inside a “chroot gaol”
              as a means of limiting the system's exposure to rogue behaviour
              by the process. Note that the specified directory needs to
              already be set up for this purpose.

            * Set the process UID and GID to the `uid` and `gid` attribute
              values.

            * Close all open file descriptors. This excludes those listed in
              the `files_preserve` attribute, and those that correspond to the
              `stdin`, `stdout`, or `stderr` attributes.

            * Change current working directory to the path specified by the
              `working_directory` attribute.

            * Reset the file access creation mask to the value specified by
              the `umask` attribute.

            * If the `detach_process` option is true, detach the current
              process into its own process group, and disassociate from any
              controlling terminal.

            * Set signal handlers as specified by the `signal_map` attribute.

            * If any of the attributes `stdin`, `stdout`, `stderr` are not
              ``None``, bind the system streams `sys.stdin`, `sys.stdout`,
              and/or `sys.stderr` to the files represented by the
              corresponding attributes. Where the attribute has a file
              descriptor, the descriptor is duplicated (instead of re-binding
              the name).

            * If the `pidfile` attribute is not ``None``, enter its context
              manager.

            * Mark this instance as open (for the purpose of future `open` and
              `close` calls).

            * Register the `close` method to be called during Python's exit
              processing.

            When the function returns, the running program is a daemon
            process.
        """
        if self.is_open:
            return

        if self.chroot_directory is not None:
            change_root_directory(self.chroot_directory)

        if self.prevent_core:
            prevent_core_dump()

        change_file_creation_mask(self.umask)
        change_working_directory(self.working_directory)
        change_process_owner(self.uid, self.gid)

        if self.detach_process:
            detach_process_context()

        if self.process_name:
            setproctitle(self.process_name)

        signal_handler_map = self._make_signal_handler_map()
        set_signal_handlers(signal_handler_map)

        exclude_fds = self._get_exclude_file_descriptors()
        close_all_open_files(exclude=exclude_fds)

        self.stdin = set_std(self.stdin, os.devnull, 'r')

        same_std_out_err = self.stdout == self.stderr

        self.stdout = set_std(
            self.stdout, os.devnull,
            'wb+' if self.binary_out else 'w+'
        )
        self.stderr = self.stdout if same_std_out_err else set_std(
            self.stderr, os.devnull,
            'wb+' if self.binary_err else 'w+'
        )

        for std in ['stdin', 'stdout', 'stderr']:
            redirect_stream(std, getattr(self, std))

        if self.pidfile is not None and self.manage_pidfile:
            self.pidfile.__enter__()

        self._is_open = True

        atexit.register(self.close)

    def __enter__(self):
        """ Context manager entry point. """
        self.open()
        return self

    def close(self):
        """ Exit the daemon process context.
            :Return: ``None``

            Close the daemon context. This performs the following steps:

            * If this instance's `is_open` property is false, return
              immediately. This makes it safe to call `close` multiple times
              on an instance.

            * If the `pidfile` attribute is not ``None``, exit its context
              manager.

            * Mark this instance as closed (for the purpose of future `open`
              and `close` calls).
        """
        if not self.is_open:
            return

        if self.pidfile is not None and self.manage_pidfile:
            # Follow the interface for telling a context manager to exit,
            # <URL:http://docs.python.org/library/stdtypes.html#typecontextmanager>.
            self.pidfile.__exit__(None, None, None)

        self._is_open = False

    def __exit__(self, exc_type, exc_value, traceback):
        """ Context manager exit point. """
        self.close()

    @property
    def pid(self):
        if not self.pidfile:
            raise DaemonOSEnvironmentError('No PID file associated with daemon')

        if self.manage_pidfile:
            pid = self.pidfile.read_pid()
        else:
            try:
                with open(self.pidfile) as fp:
                    pid = int(fp.read().strip())
            except (OSError, IOError, ValueError):
                return 0

        return pid or 0

    @property
    def alive(self):
        if self.pid == 0:
            return False

        try:
            os.kill(self.pid, 0)
        except OSError:
            return False

        return True

    @property
    def _stale_path(self):
        if self.pidfile is None:
            return None

        path = self.pidfile if isinstance(
            self.pidfile, six.string_types
        ) else self.pidfile.path

        dirpath, basename = os.path.split(path)

        return os.path.join(dirpath, '.' + basename + '.stale')

    @property
    def stale(self):
        if not self.alive:
            return False

        return os.path.exists(self._stale_path)

    def mark_stale(self):
        try:
            with open(self._stale_path, 'w'):
                pass
        except (IOError, OSError):
            pass

    def terminate(self, signal_number, stack_frame):
        """ Signal handler for end-process signals.
            :Return: ``None``

            Signal handler for the ``signal.SIGTERM`` signal. Performs the
            following step:

            * Raise a ``SystemExit`` exception explaining the signal.
        """

        # Force atexit functions to run, as they don't seem to be when SystemExit is raised.
        atexit._run_exitfuncs()
        raise SystemExit('Terminating on signal {:d}'.format(signal_number))

    def _get_exclude_file_descriptors(self):
        """ Return the set of file descriptors to exclude closing.

            Returns a set containing the file descriptors for the
            items in `files_preserve`, and also each of `stdin`,
            `stdout`, and `stderr`:

            * If the item is ``None``, it is omitted from the return
              set.

            * If the item has a ``fileno()`` method, that method's
              return value is in the return set.

            * Otherwise, the item is in the return set verbatim.
        """
        files_preserve = self.files_preserve
        if files_preserve is None:
            files_preserve = []

        files_preserve.extend(
            item for item in [self.stdin, self.stdout, self.stderr] if hasattr(item, 'fileno')
        )

        exclude_descriptors = set()
        for item in files_preserve:
            if item is None:
                continue

            if hasattr(item, 'fileno'):
                exclude_descriptors.add(item.fileno())
            else:
                exclude_descriptors.add(item)
        return exclude_descriptors

    def _make_signal_handler(self, target):
        """ Make the signal handler for a specified target object.

            If `target` is ``None``, returns ``signal.SIG_IGN``. If
            `target` is a string, returns the attribute of this
            instance named by that string. Otherwise, returns `target`
            itself.
        """
        if target is None:
            return signal.SIG_IGN

        if isinstance(target, six.string_types):
            return getattr(self, target)

        return target

    def _make_signal_handler_map(self):
        """ Make the map from signals to handlers for this instance.

            Constructs a map from signal numbers to handlers for this
            context instance, suitable for passing to
            `set_signal_handlers`.
        """
        return dict(
            (signal_number, self._make_signal_handler(target))
            for signal_number, target in self.signal_map.items()
        )


def change_working_directory(directory):
    """ Change the working directory of this process."""
    try:
        os.chdir(directory)
    except OSError as exc:
        raise DaemonOSEnvironmentError('Unable to change working directory ({!s})'.format(exc))


def change_root_directory(directory):
    """ Change the root directory of this process.

        Sets the current working directory, then the process root
        directory, to the specified `directory`. Requires appropriate
        OS privileges for this process.
    """
    try:
        os.chdir(directory)
        os.chroot(directory)
    except OSError as exc:
        raise DaemonOSEnvironmentError('Unable to change root directory ({!s})'.format(exc))


def change_file_creation_mask(mask):
    """ Change the file creation mask for this process."""
    try:
        os.umask(mask)
    except OSError as exc:
        raise DaemonOSEnvironmentError('Unable to change file creation mask ({!s})'.format(exc))


def change_process_owner(uid, gid):
    """ Change the owning UID and GID of this process.

        Sets the GID then the UID of the process (in that order, to
        avoid permission errors) to the specified `gid` and `uid`
        values. Requires appropriate OS privileges for this process.
    """
    try:
        os.setgid(gid)
        os.setuid(uid)
    except OSError as exc:
        raise DaemonOSEnvironmentError('Unable to change process owner ({!s}'.format(exc))


def prevent_core_dump():
    """ Prevent this process from generating a core dump.

        Sets the soft and hard limits for core dump size to zero. On
        Unix, this prevents the process from creating core dump
        altogether.
    """
    core_resource = resource.RLIMIT_CORE

    try:
        # Ensure the resource limit exists on this platform, by requesting
        # its current value
        resource.getrlimit(core_resource)
    except ValueError as exc:
        raise DaemonOSEnvironmentError('System does not support RLIMIT_CORE resource limit ({!s})'.format(exc))

    # Set hard and soft limits to zero, i.e. no core dump at all
    core_limit = (0, 0)
    resource.setrlimit(core_resource, core_limit)


def detach_process_context():
    """ Detach the process context from parent and session.

        Detach from the parent process and session group, allowing the
        parent to exit while this process continues running.

        Reference: “Advanced Programming in the Unix Environment”,
        section 13.3, by W. Richard Stevens, published 1993 by
        Addison-Wesley.
    """

    def fork_then_exit_parent(error_message, second_fork=False):
        """ Fork a child process, then exit the parent process.

            If the fork fails, raise a ``DaemonProcessDetachError``
            with ``error_message``.

            """
        try:
            pid = os.fork()
            if pid:
                if second_fork:
                    os._exit(0)
                else:
                    os.waitpid(pid, 0)
                    sys.exit(0)
        except OSError as exc:
            raise DaemonProcessDetachError('{}: [{:d}] {}'.format(error_message, exc.errno, exc.strerror))

    fork_then_exit_parent(error_message='Failed first fork')
    os.setsid()
    fork_then_exit_parent(error_message='Failed second fork', second_fork=True)


def is_process_started_by_init():
    """ Determine if the current process is started by `init`.

        The `init` process has the process ID of 1; if that is our
        parent process ID, return ``True``, otherwise ``False``.
    """
    init_pid = 1
    if os.getppid() == init_pid:
        return True

    return False


def is_socket(fd):
    """ Determine if the file descriptor is a socket.

        Return ``False`` if querying the socket type of `fd` raises an
        error; otherwise return ``True``.
    """
    file_socket = socket.fromfd(fd, socket.AF_INET, socket.SOCK_RAW)

    try:
        file_socket.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE)
    except socket.error as exc:
        exc_errno = exc.args[0]
        if exc_errno == errno.ENOTSOCK:
            # Socket operation on non-socket
            return False

    return True


def is_process_started_by_superserver():
    """ Determine if the current process is started by the superserver.

        The internet superserver creates a network socket, and
        attaches it to the standard streams of the child process. If
        that is the case for this process, return ``True``, otherwise
        ``False``.

        """
    try:
        stdin_fd = sys.__stdin__.fileno()
        if is_socket(stdin_fd):
            return True
    except ValueError:
        pass
    except AttributeError:
        return False

    return False


def is_detach_process_context_required():
    """ Determine whether detaching process context is required.

        Return ``True`` if the process environment indicates the
        process is already detached:

        * Process was started by `init`; or

        * Process was started by `inetd`.
    """
    if is_process_started_by_init() or is_process_started_by_superserver():
        return False

    return True


def close_file_descriptor_if_open(fd, check_fd_urandom):
    """ Close a file descriptor if already open.

        Close the file descriptor `fd`, suppressing an error in the
        case the file was not open.
    """
    try:
        if check_fd_urandom and os.path.sameopenfile(fd, check_fd_urandom):
            return
    except OSError:
        pass

    try:
        os.close(fd)
    except OSError as exc:
        if exc.errno != errno.EBADF:
            raise DaemonOSEnvironmentError('Failed to close file descriptor {:d} ({!s})'.format(fd, exc))


MAXFD = 2048

def get_maximum_file_descriptors():
    """ Return the maximum number of open file descriptors for this process.

        Return the process hard resource limit of maximum number of
        open file descriptors. If the limit is “infinity”, a default
        value of ``MAXFD`` is returned.
    """
    limits = resource.getrlimit(resource.RLIMIT_NOFILE)
    maxfd = limits[1]

    if maxfd == resource.RLIM_INFINITY:
        return MAXFD

    return maxfd


def close_all_open_files(exclude=set()):
    """ Close all open file descriptors.

        Closes every file descriptor (if open) of this process. If
        specified, `exclude` is a set of file descriptors to *not*
        close.
    """
    maxfd = get_maximum_file_descriptors()
    check_fd_urandom = os.open("/dev/urandom", os.O_RDONLY) if sys.version_info[0:3] == (3, 4, 0) else None
    for fd in reversed(range(maxfd)):
        if fd not in exclude:
            close_file_descriptor_if_open(fd, check_fd_urandom)


def set_std(destination, default, mode):
    attr_check = _default_std_info[mode]['attr']
    buffering = _default_std_info[mode]['buffering']

    def get_default():
        if default and not hasattr(default, attr_check):
            return open(default, mode, buffering=buffering)
        return default

    if destination is None or hasattr(destination, attr_check):
        return destination or get_default()

    return open(destination, mode, buffering=buffering) if isinstance(destination, six.string_types) and destination else get_default()


def redirect_stream(name, target_stream):
    """ Redirect a system stream to a specified file.

        `system_stream` is a standard system stream such as
        ``sys.stdout``. `target_stream` is an open file object that
        should replace the corresponding system stream object.

        If `target_stream` is ``None``, defaults to opening the
        operating system's null device and using its file descriptor.
    """
    if target_stream is None:
        target_fd = os.open(os.devnull, os.O_RDWR)
    else:
        target_fd = target_stream.fileno()

    # dup2 fails on StringIO instances, so if we detect that,
    # force back to the actual stream

    if isinstance(getattr(sys, name), StringIO):
        setattr(sys, name, getattr(sys, '__' + name + '__'))

    src_stream = getattr(sys, name)
    if src_stream is None:
        os.dup2(target_fd, os.open(os.devnull, os.O_RDWR))
    else:
        os.dup2(target_fd, src_stream.fileno())


def make_default_signal_map():
    """ Make the default signal map for this system.

        The signals available differ by system. The map will not
        contain any signals not defined on the running system.
    """
    name_map = {
        'SIGTSTP': None,
        'SIGTTIN': None,
        'SIGTTOU': None,
        'SIGTERM': 'terminate',
    }

    return dict(
        (getattr(signal, name), target)
        for name, target in name_map.items()
        if hasattr(signal, name)
    )


def set_signal_handlers(signal_handler_map):
    """ Set the signal handlers as specified.

        The `signal_handler_map` argument is a map from signal number
        to signal handler. See the `signal` module for details.
    """
    try:
        for signal_number, handler in signal_handler_map.items():
            signal.signal(signal_number, handler)
    except ValueError as err:
        if 'main thread' not in str(err):
            raise

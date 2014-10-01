python-daemon
=============

Fork of https://pypi.python.org/pypi/python-daemon

## Fork Differences

* Python 3 Support
* `daemon.create_daemon()` function to create "service-like" daemon instance. 

## Description

Library to implement a well-behaved Unix daemon process.

This library implements the well-behaved daemon specification of
[PEP 3143: "Standard daemon process library"](http://legacy.python.org/dev/peps/pep-3143).

A well-behaved Unix daemon process is tricky to get right, but the required steps are much the same for every daemon program. A `DaemonContext` instance holds the behaviour and configured process environment for the program; use the instance as a context manager to enter a daemon state.

## Usage

**"spawn-and-exit" usage**:

```python
import daemon

from spam import do_main_program

with daemon.DaemonContext():
    do_main_program()
```

Customization of the steps to become a daemon is available by setting options on the `DaemonContext` instance; see the documentation for that class for each option.

**"spawn-and-continue" usage**:

```python
import daemon

from spam import do_main_program, do_other_stuff

# Spawned in daemon process
daemon.create_daemon(do_main_program).start()

# Continue execution of current process
do_other_stuff()
```

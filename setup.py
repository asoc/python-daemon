# -*- coding: utf-8 -*-

# setup.py
# Part of python-daemon, an implementation of PEP 3143.
#
# Copyright © 2008–2010 Ben Finney <ben+python@benfinney.id.au>
# Copyright © 2008 Robert Niederreiter, Jens Klein
#
# This is free software: you may copy, modify, and/or distribute this work
# under the terms of the Python Software Foundation License, version 2 or
# later as published by the Python Software Foundation.
# No warranty expressed or implied. See the file LICENSE.PSF-2 for details.
from __future__ import unicode_literals, print_function, absolute_import, division

import fileinput
import os
import textwrap

from setuptools import setup, find_packages


__version = os.path.join('daemon', '_version.py')
exec(open(__version).read())

distribution_name = 'python-daemon'

__init = os.path.join('daemon', '__init__.py')
__short_desc = ''
__long_desc = []
__is_doc = True

for line in fileinput.input(__init):
    if line == '"""':
        break

    if line.startswith('"""'):
        __is_doc = True
        __short_desc = line.lstrip('"')
    elif __is_doc:
        __long_desc.append(line)

__long_desc = textwrap.dedent(os.linesep.join(__long_desc)).strip()


setup(
    name=distribution_name,
    version=VERSION,
    packages=find_packages(exclude=['test']),

    # setuptools metadata
    zip_safe=False,

    install_requires=[
        'setuptools',
        'lockfile >= 0.7',
        'setproctitle',
        'six',
    ],

    # PyPI metadata
    author=AUTHOR,
    author_email=AUTHOR_EMAIL,
    description=__short_desc,
    license=LICENSE,
    keywords='daemon fork unix'.split(),
    url=URL,
    long_description=__long_desc,
    classifiers=[
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: Python Software Foundation License',
        'Operating System :: POSIX',
        'Programming Language :: Python',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)

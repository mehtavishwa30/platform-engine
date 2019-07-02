#!/usr/bin/env python
import io
import os
import sys

from setuptools import find_packages, setup


if sys.argv[-1] == 'publish':
    os.system('python setup.py sdist upload')
    os.system('python setup.py bdist_wheel upload')
    sys.exit()


readme = io.open('README.md', 'r', encoding='utf-8').read()

setup(
    name='asyncy-platform-engine',
    description='The engine of the Asyncy platform',
    long_description=readme,
    author='Asyncy',
    author_email='noreply@asyncy.com',
    version='0.2.0',
    packages=find_packages(),
    tests_require=[
        'pytest==4.2.0',
        'pytest-cov==2.6.1',
        'pytest-mock==1.10.1',
        'pytest-asyncio==0.10.0'
    ],
    setup_requires=['pytest-runner'],
    install_requires=[
        'prometheus-client==0.2.0',
        'tornado==5.0.2',
        'click==7.0',
        'frustum==0.0.6',
        'raven==6.9.0',
        'storyscript==0.20.1',
        'ujson==1.35',
        'certifi>=2018.8.24',
        'psycopg2==2.7.5',
        'numpy==1.16.4',
        'requests==2.21.0'  # Used for structures like CaseInsensitiveDict.
    ],
    classifiers=[
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3'
    ],
    entry_points="""
        [console_scripts]
        asyncy-server=asyncy.Service:Service.main
    """
)

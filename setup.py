#!/usr/bin/env python
from setuptools import setup

from hsm.hsm import __version__ as version

setup(
    name="hsm",
    version=version,
    description="Hierarchical Statemachine ",
    author="Hans Maerki",
    author_email="hans@maerki.com",
    url="https://github.com/hmaerki/HierarchicalStateMachine",
    install_requires=[],
    packages=["hsm"],
    package_data={},
    keywords=["hierarchical state machine"],
    classifiers=[],
    entry_points={"console_scripts": []},
)

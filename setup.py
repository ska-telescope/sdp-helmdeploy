#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""PIP setup script for the ska-sdp-helmdeploy package."""

import setuptools

VERSION = {}
with open("src/ska_sdp_helmdeploy/version.py", "r") as fh:
    exec(fh.read(), VERSION)

with open("README.md", "r") as fh:
    LONG_DESCRIPTION = fh.read()

setuptools.setup(
    name="ska-sdp-helmdeploy",
    version=VERSION["__version__"],
    description="Helm deployment controller",
    author="SKA Sim Team",
    license="License :: OSI Approved :: BSD License",
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    url="https://gitlab.com/ska-telescope/sdp/ska-sdp-helmdeploy/",
    package_dir={"": "src"},
    packages=setuptools.find_packages("src"),
    install_requires=[
        "python-dotenv",
        "pyyaml",
        "ska-sdp-config",
        "ska-ser-logging",
    ],
    setup_requires=["pytest-runner"],
    tests_require=[
        "pytest",
        "pytest-cov",
    ],
    zip_safe=False,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Astronomy",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3 :: Only",
        "License :: OSI Approved :: BSD License",
    ],
)

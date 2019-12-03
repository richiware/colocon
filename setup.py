#!/usr/bin/env python

from distutils.core import setup

setup(
        name='colocon',
        version='0.1',
        description='Utility to use colcon in another way',
        author='Ricardo González',
        author_mail='correoricky@gmail.com',
        packages=['colocon'],
        install_requires=['pyyaml']
        )

#!/usr/bin/env python

from setuptools import setup

setup(
        name='colocon',
        version='0.1',
        description='Utility to use colcon in another way.',
        author='Ricardo González',
        author_email='correoricky@gmail.com',
        license='Apache License, Version 2.0',
        packages=['colocon'],
        entry_points={
            'console_scripts': [
                'colocon = colocon.core:main'
                ]
            },
        install_requires=['pyyaml']
        )

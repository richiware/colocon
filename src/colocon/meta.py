# Copyright 2019 Ricardo González
# Licensed under the Apache License, Version 2.0

"""Generation of a ``colcon.meta`` carrying ``-ffile-prefix-map`` flags.

Passing ``-ffile-prefix-map`` per package makes the compiler record relative
paths, so that build artifacts do not depend on where each worktree lives.

Nothing calls this module at the moment: generating ``colcon.meta`` was
switched off, and `colocon` no longer passes ``--meta`` to ``colcon``. It is
kept because the behaviour is still a requirement in ``doc/design.md``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

import yaml


def generate_colcon_meta(build_dir: str, meta_paths: Mapping[str, str]) -> None:
    """Write ``{build_dir}/colcon.meta`` adding the prefix map of each package."""
    yaml_content = None
    colcon_meta_path = Path('colcon.meta')
    if colcon_meta_path.is_file():
        yaml_content = yaml.safe_load(colcon_meta_path.read_text())

    if not yaml_content:
        yaml_content = {'names': {}}

    for lib in meta_paths:
        if lib not in yaml_content['names']:
            yaml_content['names'][lib] = {}
        if 'cmake-args' not in yaml_content['names'][lib]:
            yaml_content['names'][lib]['cmake-args'] = []
        yaml_content['names'][lib]['cmake-args'] += [
            '-DCMAKE_CXX_FLAGS=-ffile-prefix-map=' + meta_paths[lib] + '=.',
            '-DCMAKE_C_FLAGS=-ffile-prefix-map=' + meta_paths[lib] + '=.',
        ]

        if not os.path.exists(build_dir):
            os.makedirs(build_dir)
        with open(build_dir + '/colcon.meta', 'w') as file:
            yaml.dump(yaml_content, file)

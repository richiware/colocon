# Copyright 2019 Ricardo González
# Licensed under the Apache License, Version 2.0

"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from colocon.config import load_config
from colocon.resolve import read_project_info, read_repositories, resolve_paths
from colocon.runner import build_argv, merge_compile_commands, run_colcon


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse `colocon`'s own arguments, leaving the rest for ``colcon``."""
    parser = argparse.ArgumentParser(
            prog='colocon',
            description='Helper to run colcon in different way.')
    parser.add_argument(
            '-p', '--project-dir', default='.',
            help='Root directory of the main project, where its CMakeList.txt will be found.')
    parser.add_argument(
            '-a', '--all', action='store_true',
            help='Instead of inner-join between dependencies of "colcon.pkg" and "{project_name}.repos",\
             a left-join will be done and use all dependencies')
    parser.add_argument('rest', nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run `colocon`.

    Logic:

    * Get arguments
    * Get default values from configuration
    * Read colcon.pkg and get project
    * Read {project_name}.repos and get dependencies versions
    * Generate colcon paths to pass using '--paths'
    * Prepare arguments and call colcon

    :param argv: The list of arguments, defaulting to ``sys.argv[1:]``
    :returns: The return code
    """
    options = parse_args(argv)
    config = load_config()

    project_info = read_project_info(options.project_dir)
    if project_info is None:
        print('Cannot get info from colcon.pkg', file=sys.stderr)
        return 1

    repositories = read_repositories(options.project_dir, project_info.name)
    resolved = resolve_paths(
            options.project_dir, project_info, repositories, config.search_paths, include_all=options.all)
    for name in resolved.missing:
        print('Cannot find path for ' + name, file=sys.stderr)

    if not options.rest:
        print('No colcon verb given', file=sys.stderr)
        return 1

    try:
        colcon_argv, build_dir = build_argv(options.rest, resolved)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    retcode = run_colcon(colcon_argv)
    if retcode != 0:
        return retcode

    if config.compile_commands:
        merge_compile_commands(build_dir)

    return 0

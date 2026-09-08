# Copyright 2019 Ricardo González
# Licensed under the Apache License, Version 2.0

"""Construction and invocation of the underlying ``colcon`` command line."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence

from colocon.resolve import ResolvedPaths

#: Mixin used when the user asks for none.
DEFAULT_MIXIN = 'rel-with-deb-info'

#: Verbs that accept ``--paths`` and ``--base-paths``.
PATH_VERBS = frozenset({'build', 'test', 'graph'})

#: Exit code conventionally reported for a command killed by SIGINT.
INTERRUPTED_RETURN_CODE = 130


def supports_paths(verb: str) -> bool:
    """Whether `verb` accepts the path selection arguments."""
    return verb in PATH_VERBS


def _option_value(args: Sequence[str], name: str) -> str:
    """Return the value following `name` in `args`."""
    position = args.index(name)
    if position + 1 >= len(args):
        raise ValueError(name + ' requires a value')
    return args[position + 1]


def _take_option(args: list, name: str) -> str | None:
    """Remove `name` and its value from `args`, returning the value.

    Returns ``None`` when `name` is absent.
    """
    if name not in args:
        return None
    position = args.index(name)
    value = _option_value(args, name)
    del args[position:position + 2]
    return value


def build_argv(
    rest: Sequence[str],
    resolved: ResolvedPaths,
    platform: str | None = None,
) -> tuple[list, str]:
    """Build the ``colcon`` command line.

    `rest` is the verb followed by the arguments meant for ``colcon``. Returns
    the command line and the build directory it uses, which the caller needs to
    collect the compilation databases afterwards.
    """
    if not rest:
        raise ValueError('no colcon verb given')

    platform = sys.platform if platform is None else platform
    verb = rest[0]
    forwarded = list(rest[1:])
    argv = ['colcon', verb]

    if supports_paths(verb):
        if resolved.paths:
            argv += ['--paths', *resolved.paths]
        if resolved.recursive_paths:
            argv += ['--base-paths', *resolved.recursive_paths]

    # The mixin doubles as the build directory suffix, so that every build type
    # gets its own directory. Only `build` understands --mixin; for any other
    # verb the argument is left in `forwarded` and passed through untouched.
    build_suffix = DEFAULT_MIXIN
    if verb == 'build':
        mixin = _take_option(forwarded, '--mixin')
        if mixin is not None:
            build_suffix = mixin
        argv += ['--mixin', build_suffix]

    build_dir = 'build'
    if '--build-base' in forwarded:
        build_dir = _option_value(forwarded, '--build-base')
    elif platform != 'win32':
        # On Windows colcon's own default build directory is kept.
        build_dir = 'build-' + build_suffix
        argv += ['--build-base', build_dir]

    if '--install-base' not in forwarded and verb != 'graph':
        argv += ['--install-base', build_dir + '/install']

    return argv + forwarded, build_dir


def run_colcon(argv: Sequence[str]) -> int:
    """Run `argv`, returning its exit code."""
    try:
        return subprocess.call(list(argv))
    except KeyboardInterrupt:
        return INTERRUPTED_RETURN_CODE


def merge_compile_commands(build_dir: str) -> None:
    """Join every ``compile_commands.json`` under `build_dir` into one."""
    find_proc = subprocess.Popen(
            'find ' + build_dir + ' -iname compile_commands.json -print0 | grep -z . | xargs -0',
            stdout=subprocess.PIPE, shell=True)
    find_proc.wait()
    stdout = find_proc.stdout
    list_files = stdout.readline().decode('utf-8').rstrip() if stdout else ''
    find_proc.communicate()
    retcode = find_proc.returncode

    if retcode == 0:
        subprocess.call('jq -s add ' + list_files + ' > compile_commands.json', shell=True)

# Copyright 2019 Ricardo González
# Licensed under the Apache License, Version 2.0

"""Construction and invocation of the underlying ``colcon`` command line."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from colocon.resolve import ResolvedPaths

#: Mixin used when the user asks for none.
DEFAULT_MIXIN = 'rel-with-deb-info'

#: Verbs that accept ``--paths`` and ``--base-paths``.
PATH_VERBS = frozenset({'build', 'test', 'graph'})

#: Verbs that accept ``--build-base`` and ``--install-base``.
BASE_VERBS = frozenset({'build', 'test'})

#: Build directory colcon uses when it is not told otherwise, which is where
#: the compilation databases are looked for unless a ``--build-base`` was
#: configured or passed.
COLCON_BUILD_DIR = 'build'

#: Exit code conventionally reported for a command killed by SIGINT.
INTERRUPTED_RETURN_CODE = 130

#: Name of the compilation databases colcon leaves behind.
COMPILE_COMMANDS = 'compile_commands.json'


def supports_paths(verb: str) -> bool:
    """Whether `verb` accepts the path selection arguments."""
    return verb in PATH_VERBS


def _has_option(args: Sequence[str], name: str) -> bool:
    """Whether `name` is in `args`, either alone or as ``name=value``."""
    return any(arg == name or arg.startswith(name + '=') for arg in args)


def _option_value(args: Sequence[str], name: str) -> str:
    """Return the value given to `name` in `args`, the last one if repeated."""
    value = None
    for position, arg in enumerate(args):
        if arg == name:
            if position + 1 >= len(args):
                raise ValueError(name + ' requires a value')
            value = args[position + 1]
        elif arg.startswith(name + '='):
            value = arg[len(name) + 1:]
    if value is None:
        raise ValueError(name + ' is not given')
    return value


def build_argv(
        rest: Sequence[str], resolved: ResolvedPaths,
        build_base: str | Path | None = None,
        install_base: str | Path | None = None) -> tuple[list, str]:
    """Build the ``colcon`` command line.

    `rest` is the verb followed by the arguments meant for ``colcon``. Returns
    the command line and the build directory, which the caller needs to collect
    the compilation databases afterwards.

    `build_base` and `install_base` are the directories of the configuration.
    Each is passed as ``--build-base`` or ``--install-base`` to the verbs
    accepting them, unless the user passed that option, which is then
    forwarded untouched and wins. Without either, the choice is `colcon`'s.
    """
    if not rest:
        raise ValueError('no colcon verb given')

    verb = rest[0]
    forwarded = list(rest[1:])
    argv = ['colcon', verb]

    if supports_paths(verb):
        if resolved.paths:
            argv += ['--paths', *resolved.paths]
        if resolved.recursive_paths:
            argv += ['--base-paths', *resolved.recursive_paths]

    # Only `build` understands --mixin. A mixin the user asked for is left in
    # `forwarded`, so it reaches colcon exactly as it was written.
    if verb == 'build' and '--mixin' not in forwarded:
        argv += ['--mixin', DEFAULT_MIXIN]

    build_dir = COLCON_BUILD_DIR
    if _has_option(forwarded, '--build-base'):
        build_dir = _option_value(forwarded, '--build-base')
    elif verb in BASE_VERBS and build_base is not None:
        build_dir = str(build_base)
        argv += ['--build-base', build_dir]

    if verb in BASE_VERBS and install_base is not None and not _has_option(forwarded, '--install-base'):
        argv += ['--install-base', str(install_base)]

    return argv + forwarded, build_dir


def run_colcon(argv: Sequence[str]) -> int:
    """Run `argv`, returning its exit code."""
    # colcon writes to the same descriptors, so whatever colocon has already
    # printed has to be out of the buffer before it starts.
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        return subprocess.call(list(argv))
    except KeyboardInterrupt:
        return INTERRUPTED_RETURN_CODE


def merge_compile_commands(build_dir: str, output_path: str | Path = COMPILE_COMMANDS) -> int:
    """Join every compilation database under `build_dir` into `output_path`.

    Every ``compile_commands.json`` produced by the packages is concatenated
    into a single one, so that language servers see the whole project. Returns
    the number of databases merged; `output_path` is left untouched when there
    is none.
    """
    output = Path(output_path)
    databases = sorted(
        database for database in Path(build_dir).rglob(COMPILE_COMMANDS)
        if database.resolve() != output.resolve()
    )
    if not databases:
        return 0

    entries: list = []
    for database in databases:
        entries += json.loads(database.read_text())

    output.write_text(json.dumps(entries, indent=2))
    return len(databases)

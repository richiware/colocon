# Copyright 2019 Ricardo González
# Licensed under the Apache License, Version 2.0

"""A drawing of what `colocon` made of a project, to look at when it is wrong.

Nothing here decides anything: the tree is built with the very functions that
resolve the paths handed to `colcon`, so that it cannot describe a resolution
other than the one that happens.
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from colocon.resolve import (
    Location,
    Origin,
    ProjectInfo,
    Repository,
    dependency_location,
    find_worktree,
)


@dataclasses.dataclass(frozen=True)
class Glyphs:
    """The pieces a tree is drawn with."""

    branch: str
    last: str
    pipe: str
    blank: str


#: Box drawing, for a terminal that can show it.
UNICODE = Glyphs(branch='├─ ', last='└─ ', pipe='│  ', blank='   ')

#: The same tree for a terminal that cannot.
ASCII = Glyphs(branch='|- ', last='`- ', pipe='|  ', blank='   ')

#: Shown instead of a version when the repository is unknown.
NO_VERSION = '-'


def glyphs_for(stream: object) -> Glyphs:
    """The richest glyphs `stream` is able to carry."""
    encoding = getattr(stream, 'encoding', None) or 'ascii'
    try:
        (UNICODE.branch + UNICODE.last + UNICODE.pipe).encode(encoding)
    except (UnicodeEncodeError, LookupError):
        return ASCII
    return UNICODE


def contract(path: str | Path) -> str:
    """Write `path` with ``~`` for the home directory, as the documentation does."""
    text = str(path)
    home = str(Path.home())
    if text == home:
        return '~'
    if text.startswith(home + os.sep):
        return '~' + text[len(home):]
    return text


def format_origin(origin: Origin, project_dir: Path | None = None) -> str:
    """Say where a dependency was declared.

    The file is written relative to `project_dir` when it lies inside it, as
    every declaration `colocon` reads does, and the place within it is either
    the key of a ``colcon.pkg`` or the line of a ``CMakeLists.txt``.
    """
    if project_dir is not None and origin.file.is_relative_to(project_dir):
        text = origin.file.relative_to(project_dir).as_posix()
    else:
        text = contract(origin.file)
    return f'{text} ({origin.key})' if origin.key else f'{text}:{origin.line}'


@dataclasses.dataclass(frozen=True)
class _Row:
    """One dependency, and what became of it."""

    name: str
    version: str
    target: str
    note: str = ''

    def render(self, widths: tuple[int, int, int]) -> str:
        name_width, version_width, target_width = widths
        line = '  '.join([
            self.name.ljust(name_width),
            self.version.ljust(version_width),
            self.target.ljust(target_width) if self.note else self.target,
        ])
        if self.note:
            line += f'  ({self.note})'
        return line.rstrip()


def _dependency_row(
    dependency: str,
    repositories: Mapping[str, Repository],
    search_paths: Sequence[Path],
    locations: Mapping[str, Location] | None,
    repos_file: str,
) -> _Row:
    """Follow one dependency the same way `resolve_paths` does."""
    repository_name, path = dependency_location(dependency, locations)

    notes = []
    if repository_name != dependency:
        notes.append('in ' + repository_name)

    repository = repositories.get(repository_name)
    if repository is None:
        return _Row(dependency, NO_VERSION, 'not listed in ' + repos_file, ', '.join(notes))

    if repository.recursive:
        notes.append('recursive')
    note = ', '.join(notes)

    worktree = find_worktree(repository, search_paths)
    if worktree is None:
        return _Row(dependency, repository.version, 'no worktree under the search paths', note)

    directory = worktree / path if path else worktree
    if not directory.is_dir():
        return _Row(dependency, repository.version, contract(directory),
                    ', '.join(filter(None, [note, 'not found'])))

    return _Row(dependency, repository.version, contract(directory), note)


def _section(
    title: str,
    children: Sequence[tuple[str, Sequence[str]]],
    last: bool,
    glyphs: Glyphs,
) -> list[str]:
    """Draw one branch of the tree, `title` with `children` hanging off it.

    Each child is a line and the lines hanging off it in turn, which is how a
    dependency carries the place it was declared.
    """
    lines = [(glyphs.last if last else glyphs.branch) + title]
    prefix = glyphs.blank if last else glyphs.pipe
    rows = list(children) or [('(none)', ())]
    for index, (child, grandchildren) in enumerate(rows):
        child_last = index == len(rows) - 1
        lines.append(prefix + (glyphs.last if child_last else glyphs.branch) + child)
        deeper = prefix + (glyphs.blank if child_last else glyphs.pipe)
        grandchildren = list(grandchildren)
        for position, grandchild in enumerate(grandchildren):
            connector = glyphs.last if position == len(grandchildren) - 1 else glyphs.branch
            lines.append(deeper + connector + grandchild)
    return lines


def format_tree(
    project_info: ProjectInfo,
    repositories: Mapping[str, Repository],
    search_paths: Sequence[Path],
    locations: Mapping[str, Location] | None = None,
    project_dir: Path | None = None,
    glyphs: Glyphs = UNICODE,
) -> str:
    """Draw the packages of a project, its dependencies and where each resolved.

    Every dependency carries the place it was declared, written relative to
    `project_dir` when one is given.
    """
    repos_file = project_info.name + '.repos'
    search_paths = tuple(search_paths)

    rows = [
        _dependency_row(dependency, repositories, search_paths, locations, repos_file)
        for dependency in project_info.dependencies
    ]
    widths = (
        max((len(row.name) for row in rows), default=0),
        max((len(row.version) for row in rows), default=0),
        max((len(row.target) for row in rows), default=0),
    )
    package_width = max((len(package_dir.name) for package_dir in project_info.package_dirs), default=0)

    lines = [f'{project_info.name}  ({repos_file})']
    lines += _section(
            'search paths',
            [(contract(path), ()) for path in search_paths],
            False, glyphs)
    lines += _section(
            f'packages ({len(project_info.package_dirs)})',
            [(f'{package_dir.name.ljust(package_width)}  {contract(package_dir)}', ())
             for package_dir in project_info.package_dirs],
            False, glyphs)
    lines += _section(
            f'dependencies ({len(rows)})',
            [(row.render(widths), _declared_in(row.name, project_info, project_dir)) for row in rows],
            True, glyphs)
    return '\n'.join(lines)


def _declared_in(dependency: str, project_info: ProjectInfo, project_dir: Path | None) -> tuple[str, ...]:
    """The line saying where `dependency` was declared, if it is known."""
    origin = project_info.origins.get(dependency)
    if origin is None:
        return ()
    return (format_origin(origin, project_dir),)

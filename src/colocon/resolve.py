# Copyright 2019 Ricardo González
# Licensed under the Apache License, Version 2.0

"""Resolution of dependency worktrees.

The project is described by ``colcon.pkg`` (its name and dependencies) and
``{project_name}.repos`` (the version, i.e. the worktree, wanted for each
repository). Joining both and looking the result up under the configured
search paths yields the directories handed to ``colcon``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable
from pathlib import Path

import yaml

#: Worktree used when a repository declares no version, and fallback for a
#: declared version that has no worktree checked out.
DEFAULT_VERSION = 'master'

#: Keys of ``colcon.pkg`` listing dependencies, in the order they are read.
#: `colcon` lets a package narrow a dependency to one phase; whichever phase
#: needs it, its worktree has to be part of the workspace, so `colocon` takes
#: the union of them all.
DEPENDENCY_KEYS = ('dependencies', 'build-dependencies', 'run-dependencies', 'test-dependencies')

PathLike = str | Path


@dataclasses.dataclass(frozen=True)
class ProjectInfo:
    """The contents of ``colcon.pkg`` that `colocon` cares about.

    `dependencies` gathers every dependency key of the file, whatever phase it
    was declared for, with duplicates removed.
    """

    name: str
    dependencies: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class Repository:
    """One entry of the ``repositories`` mapping of a *repos* file."""

    name: str
    version: str = DEFAULT_VERSION
    recursive: bool = False


@dataclasses.dataclass(frozen=True)
class ResolvedPaths:
    """Directories to hand over to `colcon`.

    `paths` and `recursive_paths` become ``--paths`` and ``--base-paths``
    respectively; `missing` lists the dependencies whose worktree could not be
    found.
    """

    paths: tuple[str, ...] = ()
    recursive_paths: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()


def read_dependencies(content: dict) -> tuple[str, ...]:
    """Gather every dependency declared by a ``colcon.pkg``.

    The keys of `DEPENDENCY_KEYS` are read in order and their contents joined,
    keeping the first mention of a package that several phases ask for.
    """
    dependencies = []
    for key in DEPENDENCY_KEYS:
        for dependency in content.get(key) or ():
            if dependency not in dependencies:
                dependencies.append(dependency)
    return tuple(dependencies)


def read_project_info(project_dir: PathLike) -> ProjectInfo | None:
    """Read ``colcon.pkg`` from `project_dir`.

    Returns ``None`` when the file is absent or declares no ``name``.
    """
    package_path = Path(project_dir) / 'colcon.pkg'
    if not package_path.is_file():
        return None

    content = yaml.safe_load(package_path.read_text()) or {}
    name = content.get('name')
    if not name:
        return None

    return ProjectInfo(name=name, dependencies=read_dependencies(content))


def read_repositories(project_dir: PathLike, project_name: str) -> dict[str, Repository]:
    """Read ``{project_name}.repos`` from `project_dir`.

    Returns an empty mapping when the file is absent.
    """
    repos_path = Path(project_dir) / (project_name + '.repos')
    if not repos_path.is_file():
        return {}

    content = yaml.safe_load(repos_path.read_text()) or {}
    repositories = {}
    for name, spec in (content.get('repositories') or {}).items():
        spec = spec or {}
        # A version is coerced to str because YAML resolves an unquoted
        # `1.0` to a float. Quote such versions in the *repos* file, as YAML
        # would otherwise turn `1.10` into 1.1 before `colocon` sees it.
        version = spec.get('version')
        repositories[name] = Repository(
            name=name,
            version=str(version) if version else DEFAULT_VERSION,
            recursive=bool(spec.get('recursive')),
        )
    return repositories


def select_dependencies(
    repositories: dict[str, Repository],
    dependencies: Iterable[str],
) -> dict[str, Repository]:
    """Join the *repos* entries with the ``colcon.pkg`` dependencies.

    A repository is selected when the project declares it as a dependency, so
    a *repos* file may pin versions for more repositories than a given project
    needs.
    """
    wanted = set(dependencies or ())
    return {name: repository for name, repository in repositories.items() if name in wanted}


def find_worktree(repository: Repository, search_paths: Iterable[PathLike]) -> Path | None:
    """Look `repository` up under `search_paths`.

    The wanted version is tried first and `DEFAULT_VERSION` second, so a
    dependency with no worktree for that version still builds against master.
    """
    for search_path in search_paths:
        repository_path = Path(search_path) / repository.name
        if not repository_path.is_dir():
            continue
        for version in (repository.version, DEFAULT_VERSION):
            worktree = repository_path / version
            if worktree.is_dir():
                return worktree
    return None


def resolve_paths(
    project_dir: PathLike,
    project_info: ProjectInfo,
    repositories: dict[str, Repository],
    search_paths: Iterable[PathLike],
) -> ResolvedPaths:
    """Resolve the project and its dependencies to directories."""
    search_paths = tuple(search_paths)
    paths = []
    recursive_paths = []
    missing = []

    selected = select_dependencies(repositories, project_info.dependencies)
    for name, repository in selected.items():
        worktree = find_worktree(repository, search_paths)
        if worktree is None:
            missing.append(name)
            continue
        if repository.recursive:
            recursive_paths.append(str(worktree))
        else:
            paths.append(str(worktree))

    paths.append(str(Path(project_dir).resolve()))

    return ResolvedPaths(
        paths=tuple(paths),
        recursive_paths=tuple(recursive_paths),
        missing=tuple(missing),
    )

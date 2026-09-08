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

PathLike = str | Path


@dataclasses.dataclass(frozen=True)
class ProjectInfo:
    """The contents of ``colcon.pkg`` that `colocon` cares about."""

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
    respectively; `meta_paths` maps every package name (dependencies plus the
    project itself) to its directory; `missing` lists the dependencies whose
    worktree could not be found.
    """

    paths: tuple[str, ...] = ()
    recursive_paths: tuple[str, ...] = ()
    meta_paths: dict[str, str] = dataclasses.field(default_factory=dict)
    missing: tuple[str, ...] = ()


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

    return ProjectInfo(name=name, dependencies=tuple(content.get('dependencies') or ()))


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
    project_name: str,
    include_all: bool = False,
) -> dict[str, Repository]:
    """Join the *repos* entries with the ``colcon.pkg`` dependencies.

    By default this is an inner join. With `include_all` every repository is
    kept except the project itself, which `colocon` adds separately.
    """
    wanted = set(dependencies or ())
    return {
        name: repository
        for name, repository in repositories.items()
        if name in wanted or (include_all and name != project_name)
    }


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
    include_all: bool = False,
) -> ResolvedPaths:
    """Resolve the project and its dependencies to directories."""
    search_paths = tuple(search_paths)
    paths = []
    recursive_paths = []
    meta_paths = {}
    missing = []

    selected = select_dependencies(repositories, project_info.dependencies, project_info.name, include_all)
    for name, repository in selected.items():
        worktree = find_worktree(repository, search_paths)
        if worktree is None:
            missing.append(name)
            continue
        if repository.recursive:
            recursive_paths.append(str(worktree))
        else:
            paths.append(str(worktree))
        meta_paths[name] = str(worktree)

    project_path = str(Path(project_dir).resolve())
    paths.append(project_path)
    meta_paths[project_info.name] = project_path

    return ResolvedPaths(
        paths=tuple(paths),
        recursive_paths=tuple(recursive_paths),
        meta_paths=meta_paths,
        missing=tuple(missing),
    )

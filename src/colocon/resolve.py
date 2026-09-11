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
import re
from collections.abc import Callable, Iterable, Mapping
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

#: File describing a package to `colcon` directly.
COLCON_PKG = 'colcon.pkg'

#: File a CMake package is recognised by, used when no ``colcon.pkg`` says
#: anything. Its ``find_package`` commands stand in for a dependency list.
CMAKE_LISTS = 'CMakeLists.txt'

#: ``find_package(<name> ...)``. CMake command names are case insensitive and
#: may be separated from the parenthesis by blanks. A name built from a
#: variable, ``find_package(${SOME_NAME})``, matches nothing on purpose: there
#: is no way to tell what it would expand to.
FIND_PACKAGE = re.compile(r'\bfind_package\s*\(\s*"?([A-Za-z0-9_.+-]+)', re.IGNORECASE)

PathLike = str | Path


@dataclasses.dataclass(frozen=True)
class ProjectInfo:
    """What `colocon` needs to know about the project it was asked to build.

    `name` names the *repos* file. `dependencies` gathers every dependency key
    of every ``colcon.pkg`` read, whatever phase each was declared for, with
    duplicates removed. `package_dirs` are the directories to hand to `colcon`:
    the project directory for a single package project, or one directory per
    package for a project holding several.
    """

    name: str
    dependencies: tuple[str, ...] = ()
    package_dirs: tuple[Path, ...] = ()


@dataclasses.dataclass(frozen=True)
class Location:
    """Where a dependency lives, when it is no repository of its own.

    `project` is the repository to look up in the *repos* file instead of the
    dependency itself, and `path` the directory of its worktree holding the
    dependency — empty for the worktree itself.
    """

    project: str
    path: str = ''


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


def read_colcon_pkg(package_dir: PathLike) -> dict | None:
    """Read the ``colcon.pkg`` of `package_dir`.

    Returns ``None`` when the directory holds no such file, and an empty
    mapping when the file is empty.
    """
    package_path = Path(package_dir) / COLCON_PKG
    if not package_path.is_file():
        return None
    return yaml.safe_load(package_path.read_text()) or {}


def colcon_pkg_dependencies(package_dir: PathLike) -> tuple[str, ...]:
    """Dependencies the ``colcon.pkg`` of `package_dir` declares."""
    return read_dependencies(read_colcon_pkg(package_dir) or {})


def strip_cmake_comments(text: str) -> str:
    """Remove the comments of a CMake listfile.

    Both the bracket form and the line form are dropped, so that a command
    somebody commented out is not read as a dependency.
    """
    without_brackets = re.sub(r'#\[\[.*?\]\]', '', text, flags=re.DOTALL)
    return re.sub(r'#[^\n]*', '', without_brackets)


def cmake_dependencies(package_dir: PathLike) -> tuple[str, ...]:
    """Dependencies the ``CMakeLists.txt`` of `package_dir` looks for.

    Every package named by a ``find_package`` command counts as a dependency,
    keeping the first mention of a package looked for more than once. Returns
    an empty tuple when the directory holds no ``CMakeLists.txt``, as a project
    without dependencies and one without the file both resolve to nothing.
    """
    cmake_path = Path(package_dir) / CMAKE_LISTS
    if not cmake_path.is_file():
        return ()

    dependencies: list[str] = []
    for name in FIND_PACKAGE.findall(strip_cmake_comments(cmake_path.read_text(errors='replace'))):
        if name not in dependencies:
            dependencies.append(name)
    return tuple(dependencies)


def find_package_dirs(project_dir: PathLike, marker: str) -> tuple[Path, ...]:
    """Subdirectories of `project_dir`, one level down, holding a `marker` file.

    Only the first level is looked at: `colcon` crawls whatever is deeper on
    its own once it is pointed at a package.
    """
    root = Path(project_dir)
    if not root.is_dir():
        return ()
    return tuple(sorted(
        entry for entry in root.iterdir()
        if entry.is_dir() and (entry / marker).is_file()
    ))


def _project_of(
    root: Path,
    package_dirs: tuple[Path, ...],
    read: Callable[[PathLike], tuple[str, ...]],
) -> ProjectInfo:
    """Describe a project made of `package_dirs`, reading each one with `read`.

    No file states a project name in this case, so the directory holding the
    worktree provides it: the ``<repository>/<worktree>`` layout puts the
    repository name there, and the *repos* file is named after it.
    """
    dependencies: list[str] = []
    for package_dir in package_dirs:
        for dependency in read(package_dir):
            if dependency not in dependencies:
                dependencies.append(dependency)

    return ProjectInfo(
        name=root.parent.name,
        dependencies=tuple(dependencies),
        package_dirs=package_dirs,
    )


def read_project_info(project_dir: PathLike) -> ProjectInfo | None:
    """Describe the project rooted at `project_dir`.

    Four places are tried, in this order, and the first that holds a package
    describes the project:

    1. a ``colcon.pkg`` in `project_dir`, which names the project itself;
    2. a ``colcon.pkg`` in each subdirectory one level down;
    3. a ``CMakeLists.txt`` in `project_dir`;
    4. a ``CMakeLists.txt`` in each subdirectory one level down.

    A ``colcon.pkg`` states its dependencies; a ``CMakeLists.txt`` has them
    read out of its ``find_package`` commands.

    Returns ``None`` when none of the four finds a package.
    """
    root = Path(project_dir).resolve()

    content = read_colcon_pkg(root)
    if content is not None:
        name = content.get('name')
        if not name:
            return None
        return ProjectInfo(
            name=name,
            dependencies=read_dependencies(content),
            package_dirs=(root,),
        )

    package_dirs = find_package_dirs(root, COLCON_PKG)
    if package_dirs:
        return _project_of(root, package_dirs, colcon_pkg_dependencies)

    if (root / CMAKE_LISTS).is_file():
        return _project_of(root, (root,), cmake_dependencies)

    package_dirs = find_package_dirs(root, CMAKE_LISTS)
    if package_dirs:
        return _project_of(root, package_dirs, cmake_dependencies)

    return None


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


def requested_paths(
    dependencies: Iterable[str],
    locations: Mapping[str, Location] | None = None,
) -> dict[str, tuple[str, ...]]:
    """Map every repository the dependencies need to the directories wanted.

    A dependency is a repository of its own unless `locations` places it inside
    another one, in which case that project is what the *repos* file is asked
    about. The directories are relative to the worktree, and an empty one means
    the worktree itself.
    """
    requested: dict[str, list[str]] = {}
    for dependency in dependencies or ():
        location = (locations or {}).get(dependency)
        repository = location.project if location else dependency
        path = location.path if location else ''
        paths = requested.setdefault(repository, [])
        if path not in paths:
            paths.append(path)
    return {repository: tuple(paths) for repository, paths in requested.items()}


def select_dependencies(
    repositories: dict[str, Repository],
    dependencies: Iterable[str],
    locations: Mapping[str, Location] | None = None,
) -> dict[str, Repository]:
    """Join the *repos* entries with the ``colcon.pkg`` dependencies.

    A repository is selected when the project declares it as a dependency, or
    when `locations` places one of the dependencies inside it, so a *repos*
    file may pin versions for more repositories than a given project needs.
    """
    wanted = requested_paths(dependencies, locations)
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
    project_info: ProjectInfo,
    repositories: dict[str, Repository],
    search_paths: Iterable[PathLike],
    locations: Mapping[str, Location] | None = None,
) -> ResolvedPaths:
    """Resolve the project and its dependencies to directories.

    `locations` places a dependency inside another repository, so that only the
    directory holding it is used rather than the whole worktree.
    """
    search_paths = tuple(search_paths)
    paths = []
    recursive_paths = []
    missing = []

    requested = requested_paths(project_info.dependencies, locations)
    selected = select_dependencies(repositories, project_info.dependencies, locations)
    for name, repository in selected.items():
        worktree = find_worktree(repository, search_paths)
        if worktree is None:
            missing.append(name)
            continue
        for path in requested[name]:
            directory = worktree / path if path else worktree
            if not directory.is_dir():
                missing.append(name + '/' + path)
                continue
            if repository.recursive:
                recursive_paths.append(str(directory))
            else:
                paths.append(str(directory))

    paths += [str(package_dir) for package_dir in project_info.package_dirs]

    return ResolvedPaths(
        paths=tuple(paths),
        recursive_paths=tuple(recursive_paths),
        missing=tuple(missing),
    )

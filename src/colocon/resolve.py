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
from collections.abc import Callable, Iterable, Mapping, Sequence
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

#: File some projects keep their settings in, beside the ``CMakeLists.txt``
#: that includes it. Its dependencies count as the package's own.
PROJECT_SETTINGS = 'project_settings.cmake'

#: Variable of `PROJECT_SETTINGS` listing the packages to look for.
MODULE_FIND_PACKAGES = 'MODULE_FIND_PACKAGES'

#: ``set(<name> ...)``. The command name is case insensitive, the variable is
#: not, so the name is matched afterwards rather than by the pattern.
SET_COMMAND = re.compile(r'\bset\s*(\()\s*([A-Za-z0-9_]+)', re.IGNORECASE)

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
    package for a project holding several. `origins` says where each dependency
    was first declared.
    """

    name: str
    dependencies: tuple[str, ...] = ()
    package_dirs: tuple[Path, ...] = ()
    origins: dict[str, Origin] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class Origin:
    """Where a dependency was declared.

    `key` is the key of the ``colcon.pkg`` declaring it, and `line` the line of
    the ``CMakeLists.txt`` looking for it; whichever kind of file `file` is,
    only one of the two is set.
    """

    file: Path
    key: str = ''
    line: int = 0


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


def declared_dependencies(content: dict) -> tuple[tuple[str, str], ...]:
    """Gather every dependency declared by a ``colcon.pkg``, with its key.

    The keys of `DEPENDENCY_KEYS` are read in order and their contents joined,
    keeping the first mention of a package that several phases ask for.
    """
    declared: dict[str, str] = {}
    for key in DEPENDENCY_KEYS:
        for dependency in content.get(key) or ():
            declared.setdefault(dependency, key)
    return tuple(declared.items())


def read_dependencies(content: dict) -> tuple[str, ...]:
    """Gather every dependency declared by a ``colcon.pkg``."""
    return tuple(dependency for dependency, _key in declared_dependencies(content))


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


def colcon_pkg_declarations(package_dir: PathLike) -> tuple[tuple[str, Origin], ...]:
    """Dependencies of the ``colcon.pkg`` of `package_dir`, and where each is."""
    origin_file = Path(package_dir) / COLCON_PKG
    return tuple(
        (dependency, Origin(file=origin_file, key=key))
        for dependency, key in declared_dependencies(read_colcon_pkg(package_dir) or {})
    )


def cmake_declarations(package_dir: PathLike) -> tuple[tuple[str, Origin], ...]:
    """Dependencies of a CMake package, and where each of them is.

    Both files a package may state them in are read: the ``find_package``
    commands of the ``CMakeLists.txt``, and the ``MODULE_FIND_PACKAGES`` of
    the ``project_settings.cmake`` beside it, which is where a project built on
    that convention keeps them.
    """
    declarations = [
        (dependency, Origin(file=Path(package_dir) / CMAKE_LISTS, line=line))
        for dependency, line in declared_cmake_dependencies(package_dir)
    ]
    declarations += [
        (dependency, Origin(file=Path(package_dir) / PROJECT_SETTINGS, line=line))
        for dependency, line in declared_settings_dependencies(package_dir)
    ]
    return tuple(declarations)


def strip_cmake_comments(text: str) -> str:
    """Remove the comments of a CMake listfile.

    Both the bracket form and the line form are dropped, so that a command
    somebody commented out is not read as a dependency. Every line break is
    kept, a bracket comment's included, so that what is left of the file still
    numbers its lines as the file does.
    """
    without_brackets = re.sub(
            r'#\[\[.*?\]\]', lambda comment: '\n' * comment.group().count('\n'), text, flags=re.DOTALL)
    return re.sub(r'#[^\n]*', '', without_brackets)


def declared_cmake_dependencies(package_dir: PathLike) -> tuple[tuple[str, int], ...]:
    """Dependencies the ``CMakeLists.txt`` of `package_dir` looks for, and where.

    Every package named by a ``find_package`` command counts as a dependency,
    paired with the line of the command, and the first mention is the one kept
    when a package is looked for more than once. Returns nothing when the
    directory holds no ``CMakeLists.txt``.
    """
    cmake_path = Path(package_dir) / CMAKE_LISTS
    if not cmake_path.is_file():
        return ()

    text = strip_cmake_comments(cmake_path.read_text(errors='replace'))
    declared: dict[str, int] = {}
    for found in FIND_PACKAGE.finditer(text):
        declared.setdefault(found.group(1), text.count('\n', 0, found.start()) + 1)
    return tuple(declared.items())


def cmake_dependencies(package_dir: PathLike) -> tuple[str, ...]:
    """Dependencies the ``CMakeLists.txt`` of `package_dir` looks for."""
    return tuple(dependency for dependency, _line in declared_cmake_dependencies(package_dir))


def _closing_parenthesis(text: str, opening: int) -> int:
    """Index of the parenthesis closing the one at `opening`."""
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == '(':
            depth += 1
        elif text[index] == ')':
            depth -= 1
            if depth == 0:
                return index
    return len(text)


def declared_settings_dependencies(package_dir: PathLike) -> tuple[tuple[str, int], ...]:
    """Dependencies listed by the ``project_settings.cmake`` of `package_dir`.

    Every name of a ``set(MODULE_FIND_PACKAGES ...)`` counts as a dependency,
    paired with the line naming it, and the first mention is the one kept. The
    variable is commonly set more than once, a platform adding to what it
    already held, so every such command is read.

    A name `colocon` cannot read as a package — a variable, the
    ``${MODULE_FIND_PACKAGES}`` of such an addition included, or a generator
    expression — is passed over, since there is no telling what it stands for.
    Returns nothing when the directory holds no ``project_settings.cmake``.
    """
    settings_path = Path(package_dir) / PROJECT_SETTINGS
    if not settings_path.is_file():
        return ()

    text = strip_cmake_comments(settings_path.read_text(errors='replace'))
    declared: dict[str, int] = {}
    for command in SET_COMMAND.finditer(text):
        if command.group(2) != MODULE_FIND_PACKAGES:
            continue
        body = text[command.end():_closing_parenthesis(text, command.start(1))]
        for token in re.finditer(r'\S+', body):
            name = token.group().strip('"\'')
            if not name or any(character in name for character in '$<>{}'):
                continue
            declared.setdefault(name, text.count('\n', 0, command.end() + token.start()) + 1)
    return tuple(declared.items())


def settings_dependencies(package_dir: PathLike) -> tuple[str, ...]:
    """Dependencies the ``project_settings.cmake`` of `package_dir` lists."""
    return tuple(dependency for dependency, _line in declared_settings_dependencies(package_dir))


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
    read: Callable[[PathLike], tuple[tuple[str, Origin], ...]],
) -> ProjectInfo:
    """Describe a project made of `package_dirs`, reading each one with `read`.

    No file states a project name in this case, so the directory holding the
    worktree provides it: the ``<repository>/<worktree>`` layout puts the
    repository name there, and the *repos* file is named after it.
    """
    origins: dict[str, Origin] = {}
    for package_dir in package_dirs:
        for dependency, origin in read(package_dir):
            origins.setdefault(dependency, origin)

    return ProjectInfo(
        name=root.parent.name,
        dependencies=tuple(origins),
        package_dirs=package_dirs,
        origins=origins,
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
        origins = {
            dependency: Origin(file=root / COLCON_PKG, key=key)
            for dependency, key in declared_dependencies(content)
        }
        return ProjectInfo(
            name=name,
            dependencies=tuple(origins),
            package_dirs=(root,),
            origins=origins,
        )

    package_dirs = find_package_dirs(root, COLCON_PKG)
    if package_dirs:
        return _project_of(root, package_dirs, colcon_pkg_declarations)

    if (root / CMAKE_LISTS).is_file():
        return _project_of(root, (root,), cmake_declarations)

    package_dirs = find_package_dirs(root, CMAKE_LISTS)
    if package_dirs:
        return _project_of(root, package_dirs, cmake_declarations)

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


def dependency_location(dependency: str, locations: Mapping[str, Location] | None = None) -> tuple[str, str]:
    """The repository `dependency` needs, and the directory wanted from it.

    A dependency is a repository of its own unless `locations` places it inside
    another one. The directory is relative to the worktree, and empty means the
    worktree itself.
    """
    location = (locations or {}).get(dependency)
    if location is None:
        return dependency, ''
    return location.project, location.path


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
        repository, path = dependency_location(dependency, locations)
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


def dependency_directory(
    dependency: str,
    repositories: Mapping[str, Repository],
    search_paths: Sequence[PathLike],
    locations: Mapping[str, Location] | None = None,
) -> Path | None:
    """The directory `dependency` resolves to, or ``None`` when it has none.

    The happy path of `resolve_paths`, for a caller with nothing to say about
    why a dependency did not resolve.
    """
    repository_name, path = dependency_location(dependency, locations)
    repository = repositories.get(repository_name)
    if repository is None:
        return None

    worktree = find_worktree(repository, search_paths)
    if worktree is None:
        return None

    directory = worktree / path if path else worktree
    return directory if directory.is_dir() else None


def expand_dependencies(
    project_info: ProjectInfo,
    repositories: Mapping[str, Repository],
    search_paths: Sequence[PathLike],
    locations: Mapping[str, Location] | None = None,
) -> ProjectInfo:
    """Follow the dependencies of the dependencies, to the end of the chain.

    A dependency that resolves to a worktree is described the same way the
    project is, and whatever it declares becomes a dependency of the project
    too — a project therefore needs to name only what it uses directly, and
    `colcon` is handed the whole chain.

    Versions stay the business of the project's own *repos* file, the one a
    developer controls, rather than of whatever each dependency pins for
    itself. A dependency already found is never followed a second time, which
    is what keeps a chain that leads back on itself from going round.
    """
    search_paths = tuple(search_paths)
    origins = dict(project_info.origins)
    dependencies = list(project_info.dependencies)

    following = list(project_info.dependencies)
    while following:
        further = []
        for dependency in following:
            directory = dependency_directory(dependency, repositories, search_paths, locations)
            if directory is None:
                continue
            declared = read_project_info(directory)
            if declared is None:
                continue
            for found, origin in declared.origins.items():
                if found in origins or found in dependencies:
                    continue
                origins[found] = origin
                dependencies.append(found)
                further.append(found)
        following = further

    return dataclasses.replace(
            project_info, dependencies=tuple(dependencies), origins=origins)


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

# Copyright 2019 Ricardo González
# Licensed under the Apache License, Version 2.0

"""User level defaults, read from ``~/.colcon/colocon.yaml``."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import yaml

from colocon.resolve import Location

DEFAULTS_PATH = Path('.colcon') / 'colocon.yaml'

#: Key holding the dependencies that live inside another repository.
LOCATIONS_KEY = 'dependency-locations'


@dataclasses.dataclass(frozen=True)
class Config:
    """Options that do not come from the command line."""

    search_paths: tuple[Path, ...] = ()
    compile_commands: bool = False
    dependency_locations: dict[str, Location] = dataclasses.field(default_factory=dict)


def default_config_path() -> Path:
    """Return the path of the user's configuration file."""
    return Path.home() / DEFAULTS_PATH


def read_locations(content: dict) -> dict[str, Location]:
    """Read the ``dependency-locations`` mapping of a configuration file.

    A dependency may name its project directly, or a mapping stating the
    ``project`` and optionally the ``path`` of the directory holding it inside
    the worktree. Without a ``path`` the dependency's own name is used, and a
    ``path`` of ``.`` means the worktree itself.

    Raises `ValueError` on an entry `colocon` cannot make sense of.
    """
    locations = {}
    for dependency, spec in (content.get(LOCATIONS_KEY) or {}).items():
        if spec is None:
            spec = {}
        if isinstance(spec, str):
            project: object = spec
            path: object = dependency
        elif isinstance(spec, dict):
            project = spec.get('project')
            path = spec.get('path')
            if path is None:
                path = dependency
        else:
            raise ValueError(
                    f"{LOCATIONS_KEY}: '{dependency}' must name its project, or state it in a mapping")
        if not project:
            raise ValueError(f"{LOCATIONS_KEY}: '{dependency}' declares no project")

        path = str(path)
        if Path(path).is_absolute():
            raise ValueError(
                    f"{LOCATIONS_KEY}: the path of '{dependency}' must be relative to the worktree")
        locations[dependency] = Location(project=str(project), path='' if path == '.' else path)

    return locations


def load_config(path: str | Path | None = None) -> Config:
    """Load the configuration from `path`, falling back to the user's file.

    A missing or empty file yields a `Config` with its default values. A search
    path starting with ``~`` is expanded, as a configuration file is written by
    hand and never goes through a shell.

    Raises `ValueError` when the file states something `colocon` cannot make
    sense of.
    """
    config_path = default_config_path() if path is None else Path(path)
    if not config_path.is_file():
        return Config()

    content = yaml.safe_load(config_path.read_text()) or {}
    return Config(
        search_paths=tuple(Path(search_path).expanduser() for search_path in content.get('search-paths') or ()),
        compile_commands=bool(content.get('compile_commands', False)),
        dependency_locations=read_locations(content),
    )

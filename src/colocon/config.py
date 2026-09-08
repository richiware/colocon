# Copyright 2019 Ricardo González
# Licensed under the Apache License, Version 2.0

"""User level defaults, read from ``~/.colcon/colocon.yaml``."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import yaml

DEFAULTS_PATH = Path('.colcon') / 'colocon.yaml'


@dataclasses.dataclass(frozen=True)
class Config:
    """Options that do not come from the command line."""

    search_paths: tuple[Path, ...] = ()
    compile_commands: bool = False


def default_config_path() -> Path:
    """Return the path of the user's configuration file."""
    return Path.home() / DEFAULTS_PATH


def load_config(path: str | Path | None = None) -> Config:
    """Load the configuration from `path`, falling back to the user's file.

    A missing or empty file yields a `Config` with its default values.
    """
    config_path = default_config_path() if path is None else Path(path)
    if not config_path.is_file():
        return Config()

    content = yaml.safe_load(config_path.read_text()) or {}
    return Config(
        search_paths=tuple(Path(search_path) for search_path in content.get('search-paths') or ()),
        compile_commands=bool(content.get('compile_commands', False)),
    )

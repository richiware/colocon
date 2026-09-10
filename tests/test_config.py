# Copyright 2019 Ricardo González
# Licensed under the Apache License, Version 2.0

import dataclasses
from pathlib import Path

import pytest

from colocon.config import Config, load_config


def test_missing_file_yields_defaults(tmp_path):
    assert load_config(tmp_path / 'absent.yaml') == Config()


def test_empty_file_yields_defaults(tmp_path):
    config_path = tmp_path / 'colocon.yaml'
    config_path.write_text('')
    assert load_config(config_path) == Config()


def test_loads_search_paths_and_compile_commands(tmp_path):
    config_path = tmp_path / 'colocon.yaml'
    config_path.write_text('search-paths: ["/a", "/b"]\ncompile_commands: true\n')

    config = load_config(config_path)

    assert config.search_paths == (Path('/a'), Path('/b'))
    assert config.compile_commands is True


def test_compile_commands_defaults_to_false(tmp_path):
    config_path = tmp_path / 'colocon.yaml'
    config_path.write_text('search-paths: ["/a"]\n')

    assert load_config(config_path).compile_commands is False


def test_tilde_is_expanded(tmp_path):
    config_path = tmp_path / 'colocon.yaml'
    config_path.write_text('search-paths: ["~/repos"]\n')

    assert load_config(config_path).search_paths == (Path.home() / 'repos',)


def test_absolute_paths_are_kept(tmp_path):
    config_path = tmp_path / 'colocon.yaml'
    config_path.write_text('search-paths: ["/opt/vendor/repos"]\n')

    assert load_config(config_path).search_paths == (Path('/opt/vendor/repos'),)


def test_environment_variables_are_not_expanded(tmp_path):
    # Only `~` is expanded; a `$VAR` reaches the lookup as written.
    config_path = tmp_path / 'colocon.yaml'
    config_path.write_text('search-paths: ["$HOME/repos"]\n')

    assert load_config(config_path).search_paths == (Path('$HOME/repos'),)


def test_search_paths_default_to_empty(tmp_path):
    config_path = tmp_path / 'colocon.yaml'
    config_path.write_text('compile_commands: true\n')

    assert load_config(config_path).search_paths == ()


def test_config_is_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        Config().compile_commands = True

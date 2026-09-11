# Copyright 2019 Ricardo González
# Licensed under the Apache License, Version 2.0

import dataclasses
from pathlib import Path

import pytest

from colocon.config import Config, load_config
from colocon.resolve import Location


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


class TestDependencyLocations:
    """Dependencies that live inside another repository."""

    def load(self, tmp_path, body):
        config_path = tmp_path / 'colocon.yaml'
        config_path.write_text(body)
        return load_config(config_path)

    def test_absent_key(self, tmp_path):
        assert self.load(tmp_path, 'search-paths: ["/a"]\n').dependency_locations == {}

    def test_path_defaults_to_the_dependency_name(self, tmp_path):
        config = self.load(tmp_path, """
            dependency-locations:
              stardust_core:
                project: stardust
            """)

        assert config.dependency_locations == {
            'stardust_core': Location(project='stardust', path='stardust_core')}

    def test_explicit_path(self, tmp_path):
        config = self.load(tmp_path, """
            dependency-locations:
              stardust_core:
                project: stardust
                path: core
            """)

        assert config.dependency_locations == {'stardust_core': Location(project='stardust', path='core')}

    def test_nested_path(self, tmp_path):
        config = self.load(tmp_path, """
            dependency-locations:
              stardust_core:
                project: stardust
                path: src/core
            """)

        assert config.dependency_locations['stardust_core'].path == 'src/core'

    def test_a_dot_path_means_the_worktree_itself(self, tmp_path):
        config = self.load(tmp_path, """
            dependency-locations:
              stardust_core:
                project: stardust
                path: .
            """)

        assert config.dependency_locations['stardust_core'] == Location(project='stardust', path='')

    def test_shorthand_names_the_project(self, tmp_path):
        config = self.load(tmp_path, """
            dependency-locations:
              stardust_core: stardust
            """)

        assert config.dependency_locations == {
            'stardust_core': Location(project='stardust', path='stardust_core')}

    def test_several_dependencies_of_one_project(self, tmp_path):
        config = self.load(tmp_path, """
            dependency-locations:
              stardust_core:
                project: stardust
                path: core
              stardust_utils:
                project: stardust
            """)

        assert config.dependency_locations == {
            'stardust_core': Location(project='stardust', path='core'),
            'stardust_utils': Location(project='stardust', path='stardust_utils'),
        }

    def test_numeric_path_is_read_as_text(self, tmp_path):
        config = self.load(tmp_path, """
            dependency-locations:
              stardust_core:
                project: stardust
                path: 2
            """)

        assert config.dependency_locations['stardust_core'].path == '2'

    def test_without_a_project(self, tmp_path):
        with pytest.raises(ValueError, match='stardust_core'):
            self.load(tmp_path, """
                dependency-locations:
                  stardust_core:
                    path: core
                """)

    def test_empty_entry(self, tmp_path):
        with pytest.raises(ValueError, match='declares no project'):
            self.load(tmp_path, 'dependency-locations:\n  stardust_core:\n')

    def test_entry_of_an_unusable_type(self, tmp_path):
        with pytest.raises(ValueError, match='stardust_core'):
            self.load(tmp_path, 'dependency-locations:\n  stardust_core: [stardust]\n')

    def test_absolute_path_is_rejected(self, tmp_path):
        with pytest.raises(ValueError, match='relative'):
            self.load(tmp_path, """
                dependency-locations:
                  stardust_core:
                    project: stardust
                    path: /opt/stardust
                """)

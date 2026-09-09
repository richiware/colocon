# Copyright 2019 Ricardo González
# Licensed under the Apache License, Version 2.0

import pytest

from colocon import cli
from colocon.config import Config


@pytest.fixture
def colcon(monkeypatch):
    """Replace the colcon invocation, recording the command line it gets."""
    calls = []

    def run(argv):
        calls.append(list(argv))
        return run.retcode

    run.retcode = 0
    run.calls = calls
    monkeypatch.setattr(cli, 'run_colcon', run)
    return run


@pytest.fixture
def config(monkeypatch):
    """Replace the user configuration, so that no real file is read."""
    def use(**overrides):
        loaded = Config(**overrides)
        monkeypatch.setattr(cli, 'load_config', lambda: loaded)
        return loaded

    use()
    return use


class TestMain:

    def test_without_colcon_pkg(self, config, project_dir, capsys):
        assert cli.main(['-p', str(project_dir), 'build']) == 1
        assert 'colcon.pkg' in capsys.readouterr().err

    def test_without_verb(self, config, write_pkg, capsys):
        assert cli.main(['-p', str(write_pkg(name='project1'))]) == 1
        assert 'verb' in capsys.readouterr().err

    def test_option_without_value(self, config, write_pkg, capsys):
        assert cli.main(['-p', str(write_pkg(name='project1')), 'build', '--mixin']) == 2
        assert '--mixin' in capsys.readouterr().err

    def test_successful_run(self, config, colcon, write_pkg):
        assert cli.main(['-p', str(write_pkg(name='project1')), 'build']) == 0
        assert colcon.calls[0][:2] == ['colcon', 'build']

    def test_colcon_exit_code_is_propagated(self, config, colcon, write_pkg):
        colcon.retcode = 17
        assert cli.main(['-p', str(write_pkg(name='project1')), 'build']) == 17

    def test_missing_dependency_is_reported(self, config, colcon, search_path, write_pkg, write_repos, capsys):
        config(search_paths=(search_path,))
        write_repos('project1', {'project9': {'version': 'master'}})
        project_dir = write_pkg(name='project1', dependencies=['project9'])

        # A dependency that cannot be located is a warning, not a failure.
        assert cli.main(['-p', str(project_dir), 'build']) == 0
        assert 'project9' in capsys.readouterr().err

    def test_dependencies_are_passed_to_colcon(self, config, colcon, search_path, write_pkg, write_repos):
        config(search_paths=(search_path,))
        write_repos('project1', {'project2': {'version': '2.x'}})
        project_dir = write_pkg(name='project1', dependencies=['project2'])

        assert cli.main(['-p', str(project_dir), 'build']) == 0
        assert str(search_path / 'project2' / '2.x') in colcon.calls[0]


class TestDependencyChain:
    """project1 -> project2 -> project3, driven through the command line."""

    REPOS = {
        'project2': {'version': '2.x'},
        'project3': {'version': '3.x'},
    }

    def test_whole_chain_is_passed_to_colcon(
            self, config, colcon, chain, search_path, write_pkg, write_repos):
        config(search_paths=(search_path,))
        write_repos('project1', self.REPOS)
        project_dir = write_pkg(name='project1', dependencies=['project2', 'project3'])

        assert cli.main(['-p', str(project_dir), 'build']) == 0

        argv = colcon.calls[0]
        assert argv[argv.index('--paths') + 1:argv.index('--paths') + 4] == [
            str(chain.project2), str(chain.project3), str(project_dir)]

    def test_indirect_level_is_left_to_colcon(
            self, config, colcon, chain, search_path, write_pkg, write_repos):
        config(search_paths=(search_path,))
        write_repos('project1', self.REPOS)
        project_dir = write_pkg(name='project1', dependencies=['project2'])

        assert cli.main(['-p', str(project_dir), 'build']) == 0

        argv = colcon.calls[0]
        assert str(chain.project2) in argv
        assert str(chain.project3) not in argv

    def test_all_flag_covers_the_whole_chain(
            self, config, colcon, chain, search_path, write_pkg, write_repos):
        config(search_paths=(search_path,))
        write_repos('project1', self.REPOS)
        project_dir = write_pkg(name='project1')

        assert cli.main(['-a', '-p', str(project_dir), 'build']) == 0

        argv = colcon.calls[0]
        assert str(chain.project2) in argv
        assert str(chain.project3) in argv

    def test_recursive_level_uses_base_paths(
            self, config, colcon, chain, search_path, write_pkg, write_repos):
        config(search_paths=(search_path,))
        write_repos('project1', {
            'project2': {'version': '2.x', 'recursive': True},
            'project3': {'version': '3.x'},
        })
        project_dir = write_pkg(name='project1', dependencies=['project2', 'project3'])

        assert cli.main(['-p', str(project_dir), 'build']) == 0

        argv = colcon.calls[0]
        assert argv[argv.index('--base-paths') + 1] == str(chain.project2)
        assert str(chain.project3) in argv


class TestCompileCommands:

    def test_not_joined_when_disabled(self, config, colcon, monkeypatch, write_pkg):
        called = []
        monkeypatch.setattr(cli, 'merge_compile_commands', lambda build_dir: called.append(build_dir))

        cli.main(['-p', str(write_pkg(name='project1')), 'build'])

        assert called == []

    def test_joined_when_enabled(self, config, colcon, monkeypatch, write_pkg):
        config(compile_commands=True)
        called = []
        monkeypatch.setattr(cli, 'merge_compile_commands', lambda build_dir: called.append(build_dir))

        cli.main(['-p', str(write_pkg(name='project1')), 'build'])

        # How the build directory is named is checked in test_runner, which is
        # the only place that pins it per platform.
        assert len(called) == 1

    def test_not_joined_when_colcon_failed(self, config, colcon, monkeypatch, write_pkg):
        config(compile_commands=True)
        colcon.retcode = 1
        called = []
        monkeypatch.setattr(cli, 'merge_compile_commands', lambda build_dir: called.append(build_dir))

        cli.main(['-p', str(write_pkg(name='project1')), 'build'])

        assert called == []

    def test_failure_to_join_does_not_fail_the_build(self, config, colcon, monkeypatch, write_pkg, capsys):
        config(compile_commands=True)

        def explode(build_dir):
            raise ValueError('broken database')

        monkeypatch.setattr(cli, 'merge_compile_commands', explode)

        assert cli.main(['-p', str(write_pkg(name='project1')), 'build']) == 0
        assert 'broken database' in capsys.readouterr().err


class TestParseArgs:

    def test_defaults(self):
        options = cli.parse_args([])
        assert options.project_dir == '.'
        assert options.all is False
        assert options.rest == []

    def test_colcon_arguments_are_kept_apart(self):
        options = cli.parse_args(['-p', 'dir', 'build', '--mixin', 'debug'])
        assert options.project_dir == 'dir'
        assert options.rest == ['build', '--mixin', 'debug']

    def test_all_flag(self):
        assert cli.parse_args(['-a', 'build']).all is True

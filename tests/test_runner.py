# Copyright 2019 Ricardo González
# Licensed under the Apache License, Version 2.0

import json

import pytest

from colocon.resolve import ResolvedPaths
from colocon.runner import (
    DEFAULT_MIXIN,
    build_argv,
    merge_compile_commands,
    supports_paths,
)

RESOLVED = ResolvedPaths(paths=('/dep', '/project'), recursive_paths=('/rec',))


def option_value(argv, name):
    """Return the value following `name` in `argv`."""
    return argv[argv.index(name) + 1]


class TestSupportsPaths:

    @pytest.mark.parametrize('verb', ['build', 'test', 'graph'])
    def test_accepting_verbs(self, verb):
        assert supports_paths(verb) is True

    @pytest.mark.parametrize('verb', ['list', 'info', 'metadata', 'version'])
    def test_rejecting_verbs(self, verb):
        assert supports_paths(verb) is False


class TestBuildArgv:

    def test_without_verb(self):
        with pytest.raises(ValueError, match='verb'):
            build_argv([], RESOLVED)

    def test_paths_are_passed(self):
        argv, _ = build_argv(['build'], RESOLVED, platform='linux')
        assert argv[:5] == ['colcon', 'build', '--paths', '/dep', '/project']

    def test_recursive_paths_use_base_paths(self):
        argv, _ = build_argv(['build'], RESOLVED, platform='linux')
        assert option_value(argv, '--base-paths') == '/rec'

    def test_no_paths_for_other_verbs(self):
        argv, _ = build_argv(['list'], RESOLVED, platform='linux')
        assert '--paths' not in argv
        assert '--base-paths' not in argv

    def test_empty_paths_are_omitted(self):
        argv, _ = build_argv(['build'], ResolvedPaths(), platform='linux')
        assert '--paths' not in argv
        assert '--base-paths' not in argv

    def test_default_mixin(self):
        argv, build_dir = build_argv(['build'], RESOLVED, platform='linux')
        assert option_value(argv, '--mixin') == DEFAULT_MIXIN
        assert build_dir == 'build-' + DEFAULT_MIXIN

    def test_requested_mixin_names_the_build_directory(self):
        argv, build_dir = build_argv(['build', '--mixin', 'debug'], RESOLVED, platform='linux')
        assert option_value(argv, '--mixin') == 'debug'
        assert build_dir == 'build-debug'
        assert option_value(argv, '--build-base') == 'build-debug'

    def test_requested_mixin_is_not_duplicated(self):
        argv, _ = build_argv(['build', '--mixin', 'debug'], RESOLVED, platform='linux')
        assert argv.count('--mixin') == 1
        assert argv.count('debug') == 1

    def test_mixin_without_value(self):
        with pytest.raises(ValueError, match='--mixin'):
            build_argv(['build', '--mixin'], RESOLVED, platform='linux')

    def test_mixin_is_forwarded_untouched_for_other_verbs(self):
        argv, _ = build_argv(['test', '--mixin', 'debug'], RESOLVED, platform='linux')
        assert argv[-2:] == ['--mixin', 'debug']

    def test_install_base_derives_from_the_build_directory(self):
        argv, _ = build_argv(['build'], RESOLVED, platform='linux')
        assert option_value(argv, '--install-base') == 'build-' + DEFAULT_MIXIN + '/install'

    def test_requested_build_base_is_respected(self):
        argv, build_dir = build_argv(['build', '--build-base', 'out'], RESOLVED, platform='linux')
        assert build_dir == 'out'
        assert argv.count('--build-base') == 1
        assert option_value(argv, '--install-base') == 'out/install'

    def test_build_base_without_value(self):
        with pytest.raises(ValueError, match='--build-base'):
            build_argv(['build', '--build-base'], RESOLVED, platform='linux')

    def test_requested_install_base_is_not_overridden(self):
        argv, _ = build_argv(['build', '--install-base', 'out'], RESOLVED, platform='linux')
        assert argv.count('--install-base') == 1
        assert option_value(argv, '--install-base') == 'out'

    def test_graph_gets_no_install_base(self):
        argv, _ = build_argv(['graph'], RESOLVED, platform='linux')
        assert '--install-base' not in argv

    def test_windows_keeps_the_colcon_build_directory(self):
        argv, build_dir = build_argv(['build'], RESOLVED, platform='win32')
        assert '--build-base' not in argv
        assert build_dir == 'build'
        assert option_value(argv, '--install-base') == 'build/install'

    def test_remaining_arguments_are_forwarded_last(self):
        argv, _ = build_argv(
                ['build', '--packages-select', 'project1', '--symlink-install'], RESOLVED, platform='linux')
        assert argv[-3:] == ['--packages-select', 'project1', '--symlink-install']

    def test_does_not_mutate_the_given_arguments(self):
        rest = ['build', '--mixin', 'debug']
        build_argv(rest, RESOLVED, platform='linux')
        assert rest == ['build', '--mixin', 'debug']


class TestMergeCompileCommands:

    def write_database(self, path, files):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([{'file': name, 'command': 'cc ' + name, 'directory': '/'} for name in files]))

    def test_joins_every_database(self, tmp_path):
        build_dir = tmp_path / 'build-debug'
        self.write_database(build_dir / 'project2' / 'compile_commands.json', ['a.cpp'])
        self.write_database(build_dir / 'project1' / 'nested' / 'compile_commands.json', ['b.cpp', 'c.cpp'])
        output = tmp_path / 'compile_commands.json'

        assert merge_compile_commands(str(build_dir), output) == 2

        entries = json.loads(output.read_text())
        assert sorted(entry['file'] for entry in entries) == ['a.cpp', 'b.cpp', 'c.cpp']

    def test_without_any_database(self, tmp_path):
        build_dir = tmp_path / 'build-debug'
        build_dir.mkdir()
        output = tmp_path / 'compile_commands.json'

        assert merge_compile_commands(str(build_dir), output) == 0
        assert not output.exists()

    def test_absent_build_directory(self, tmp_path):
        output = tmp_path / 'compile_commands.json'

        assert merge_compile_commands(str(tmp_path / 'absent'), output) == 0
        assert not output.exists()

    def test_existing_output_is_not_merged_into_itself(self, tmp_path):
        build_dir = tmp_path / 'build-debug'
        build_dir.mkdir()
        output = build_dir / 'compile_commands.json'
        self.write_database(output, ['stale.cpp'])
        self.write_database(build_dir / 'project2' / 'compile_commands.json', ['a.cpp'])

        assert merge_compile_commands(str(build_dir), output) == 1

        entries = json.loads(output.read_text())
        assert [entry['file'] for entry in entries] == ['a.cpp']

    def test_unreadable_database(self, tmp_path):
        build_dir = tmp_path / 'build-debug'
        self.write_database(build_dir / 'project2' / 'compile_commands.json', ['a.cpp'])
        (build_dir / 'project2' / 'compile_commands.json').write_text('{ not json')

        with pytest.raises(ValueError):
            merge_compile_commands(str(build_dir), tmp_path / 'compile_commands.json')

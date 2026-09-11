# Copyright 2019 Ricardo González
# Licensed under the Apache License, Version 2.0

import json
import sys

import pytest

from colocon import runner
from colocon.resolve import ResolvedPaths
from colocon.runner import (
    COLCON_BUILD_DIR,
    DEFAULT_MIXIN,
    INTERRUPTED_RETURN_CODE,
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
        argv, _ = build_argv(['build'], RESOLVED)
        assert argv[:5] == ['colcon', 'build', '--paths', '/dep', '/project']

    def test_recursive_paths_use_base_paths(self):
        argv, _ = build_argv(['build'], RESOLVED)
        assert option_value(argv, '--base-paths') == '/rec'

    def test_no_paths_for_other_verbs(self):
        argv, _ = build_argv(['list'], RESOLVED)
        assert '--paths' not in argv
        assert '--base-paths' not in argv

    def test_empty_paths_are_omitted(self):
        argv, _ = build_argv(['build'], ResolvedPaths())
        assert '--paths' not in argv
        assert '--base-paths' not in argv

    def test_remaining_arguments_are_forwarded_last(self):
        argv, _ = build_argv(['build', '--packages-select', 'project1', '--symlink-install'], RESOLVED)
        assert argv[-3:] == ['--packages-select', 'project1', '--symlink-install']

    def test_does_not_mutate_the_given_arguments(self):
        rest = ['build', '--mixin', 'debug']
        build_argv(rest, RESOLVED)
        assert rest == ['build', '--mixin', 'debug']


class TestBuildAndInstallDirectories:
    """Where colcon builds and installs is colcon's business, not colocon's."""

    @pytest.mark.parametrize('verb', ['build', 'test', 'graph', 'list'])
    def test_no_directory_is_chosen(self, verb):
        argv, build_dir = build_argv([verb], RESOLVED)

        assert '--build-base' not in argv
        assert '--install-base' not in argv
        assert build_dir == COLCON_BUILD_DIR

    def test_requested_build_base_is_forwarded_untouched(self):
        argv, build_dir = build_argv(['build', '--build-base', 'out'], RESOLVED)

        assert argv[-2:] == ['--build-base', 'out']
        assert argv.count('--build-base') == 1
        # Read only, so that the compilation databases can be found afterwards.
        assert build_dir == 'out'

    def test_requested_build_base_gains_no_install_base(self):
        argv, _ = build_argv(['build', '--build-base', 'out'], RESOLVED)
        assert '--install-base' not in argv

    def test_requested_install_base_is_forwarded_untouched(self):
        argv, _ = build_argv(['build', '--install-base', 'out'], RESOLVED)

        assert argv[-2:] == ['--install-base', 'out']
        assert argv.count('--install-base') == 1

    def test_build_base_without_value(self):
        with pytest.raises(ValueError, match='--build-base'):
            build_argv(['build', '--build-base'], RESOLVED)


class TestMixin:

    def test_default_mixin(self):
        argv, _ = build_argv(['build'], RESOLVED)
        assert option_value(argv, '--mixin') == DEFAULT_MIXIN

    def test_requested_mixin_replaces_the_default(self):
        argv, _ = build_argv(['build', '--mixin', 'debug'], RESOLVED)

        assert argv.count('--mixin') == 1
        assert option_value(argv, '--mixin') == 'debug'
        assert DEFAULT_MIXIN not in argv

    def test_requested_mixin_does_not_name_a_directory(self):
        argv, build_dir = build_argv(['build', '--mixin', 'debug'], RESOLVED)

        assert build_dir == COLCON_BUILD_DIR
        assert '--build-base' not in argv

    def test_mixin_without_value_is_left_to_colcon(self):
        # colocon no longer reads the mixin, so a malformed one is colcon's to
        # complain about.
        argv, _ = build_argv(['build', '--mixin'], RESOLVED)
        assert argv[-1] == '--mixin'

    def test_no_mixin_for_other_verbs(self):
        argv, _ = build_argv(['test'], RESOLVED)
        assert '--mixin' not in argv

    def test_mixin_is_forwarded_untouched_for_other_verbs(self):
        argv, _ = build_argv(['test', '--mixin', 'debug'], RESOLVED)

        assert argv[-2:] == ['--mixin', 'debug']
        assert argv.count('--mixin') == 1


class TestRunColcon:

    class Stream:
        """A stdout that records what happens to it."""

        encoding = 'utf-8'

        def __init__(self, events):
            self.events = events

        def write(self, text):
            self.events.append('write')
            return len(text)

        def flush(self):
            self.events.append('flush')

    def test_output_is_flushed_before_colcon_starts(self, monkeypatch):
        # colcon writes to the same descriptor, so anything colocon printed
        # first — the diagnose tree above all — has to be out of the buffer.
        events = []
        monkeypatch.setattr(runner.subprocess, 'call', lambda argv: events.append('colcon') or 0)
        monkeypatch.setattr(sys, 'stdout', self.Stream(events))

        print('printed by colocon')
        runner.run_colcon(['colcon', 'build'])

        assert events.index('write') < events.index('flush') < events.index('colcon')

    def test_the_exit_code_is_returned(self, monkeypatch):
        monkeypatch.setattr(runner.subprocess, 'call', lambda argv: 17)
        assert runner.run_colcon(['colcon', 'build']) == 17

    def test_an_interruption_is_reported(self, monkeypatch):
        def interrupt(argv):
            raise KeyboardInterrupt

        monkeypatch.setattr(runner.subprocess, 'call', interrupt)
        assert runner.run_colcon(['colcon', 'build']) == INTERRUPTED_RETURN_CODE


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

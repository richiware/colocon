# Copyright 2019 Ricardo González
# Licensed under the Apache License, Version 2.0

from pathlib import Path

import pytest

from colocon.resolve import Location, Origin, ProjectInfo, Repository
from colocon.tree import ASCII, UNICODE, contract, format_origin, format_tree, glyphs_for


def info(project_dir, *dependencies, origins=None):
    return ProjectInfo(
            name='project1',
            dependencies=dependencies,
            package_dirs=(project_dir,),
            origins=origins or {})


def row_of(text, dependency):
    """The line of `text` describing `dependency`."""
    return next(line for line in text.splitlines() if dependency in line)


class TestContract:

    def test_the_home_directory(self):
        assert contract(Path.home()) == '~'

    def test_inside_the_home_directory(self):
        assert contract(Path.home() / 'repos' / 'project2') == str(Path('~/repos/project2'))

    def test_outside_the_home_directory(self):
        assert contract(Path('/opt/vendor/repos')) == str(Path('/opt/vendor/repos'))


class TestGlyphsFor:

    class Stream:
        def __init__(self, encoding):
            self.encoding = encoding

    def test_a_stream_that_can_draw(self):
        assert glyphs_for(self.Stream('utf-8')) is UNICODE

    def test_a_stream_that_cannot(self):
        assert glyphs_for(self.Stream('ascii')) is ASCII

    def test_a_stream_without_an_encoding(self):
        assert glyphs_for(self.Stream(None)) is ASCII

    def test_an_unknown_encoding(self):
        assert glyphs_for(self.Stream('not-an-encoding')) is ASCII

    def test_something_that_is_not_a_stream(self):
        assert glyphs_for(object()) is ASCII


class TestFormatTree:

    def test_header_names_the_project_and_its_repos_file(self, project_dir):
        text = format_tree(info(project_dir), {}, [])
        assert text.splitlines()[0] == 'project1  (project1.repos)'

    def test_search_paths_are_listed_in_order(self, project_dir):
        text = format_tree(info(project_dir), {}, [Path('/a'), Path('/b')])

        assert 'search paths' in text
        assert text.index(str(Path('/a'))) < text.index(str(Path('/b')))

    def test_packages_are_listed_with_their_directories(self, project_dir):
        packages = ProjectInfo(
                name='project1',
                package_dirs=(project_dir / 'core', project_dir / 'tools'))

        text = format_tree(packages, {}, [])

        assert 'packages (2)' in text
        assert str(project_dir / 'core') in text
        assert str(project_dir / 'tools') in text

    def test_a_project_without_dependencies(self, project_dir):
        text = format_tree(info(project_dir), {}, [])
        assert 'dependencies (0)' in text
        assert '(none)' in text

    def test_a_resolved_dependency_shows_its_worktree(self, project_dir, search_path):
        repositories = {'project2': Repository(name='project2', version='2.x')}

        text = format_tree(info(project_dir, 'project2'), repositories, [search_path])

        assert str(search_path / 'project2' / '2.x') in row_of(text, 'project2')
        assert '2.x' in row_of(text, 'project2')

    def test_a_recursive_dependency_is_marked(self, project_dir, search_path):
        repositories = {'project2': Repository(name='project2', version='2.x', recursive=True)}

        text = format_tree(info(project_dir, 'project2'), repositories, [search_path])

        assert '(recursive)' in row_of(text, 'project2')

    def test_a_dependency_of_another_repository(self, project_dir, search_path):
        (search_path / 'project2' / '2.x' / 'core').mkdir()
        repositories = {'project2': Repository(name='project2', version='2.x')}
        locations = {'project2_core': Location(project='project2', path='core')}

        text = format_tree(info(project_dir, 'project2_core'), repositories, [search_path], locations)

        row = row_of(text, 'project2_core')
        assert str(search_path / 'project2' / '2.x' / 'core') in row
        assert '(in project2)' in row

    def test_a_directory_that_is_not_there(self, project_dir, search_path):
        repositories = {'project2': Repository(name='project2', version='2.x')}
        locations = {'project2_core': Location(project='project2', path='core')}

        text = format_tree(info(project_dir, 'project2_core'), repositories, [search_path], locations)

        row = row_of(text, 'project2_core')
        assert str(search_path / 'project2' / '2.x' / 'core') in row
        assert 'not found' in row

    def test_a_dependency_without_a_worktree(self, project_dir, search_path):
        repositories = {'no_worktree': Repository(name='no_worktree', version='master')}

        text = format_tree(info(project_dir, 'no_worktree'), repositories, [search_path])

        assert 'no worktree' in row_of(text, 'no_worktree')

    def test_a_dependency_absent_from_the_repos_file(self, project_dir, search_path):
        text = format_tree(info(project_dir, 'Threads'), {}, [search_path])

        assert 'not listed in project1.repos' in row_of(text, 'Threads')

    def test_columns_are_aligned(self, project_dir, search_path):
        repositories = {
            'project2': Repository(name='project2', version='2.x'),
            'project3': Repository(name='project3', version='3.x'),
        }

        text = format_tree(info(project_dir, 'project2', 'project3'), repositories, [search_path])

        rows = [row_of(text, name) for name in ('project2', 'project3')]
        assert len({row.index('3.x' if '3.x' in row else '2.x') for row in rows}) == 1

    def test_every_dependency_appears(self, project_dir, search_path):
        repositories = {'project2': Repository(name='project2', version='2.x')}
        dependencies = ('project2', 'Threads', 'no_worktree')

        text = format_tree(info(project_dir, *dependencies), repositories, [search_path])

        assert 'dependencies (3)' in text
        for dependency in dependencies:
            assert row_of(text, dependency)

    @pytest.mark.parametrize('glyphs', [UNICODE, ASCII])
    def test_both_drawings_are_complete(self, glyphs, project_dir, search_path):
        repositories = {'project2': Repository(name='project2', version='2.x')}

        text = format_tree(info(project_dir, 'project2'), repositories, [search_path], glyphs=glyphs)

        assert glyphs.branch in text
        assert glyphs.last in text
        assert glyphs.pipe in text

    def test_the_ascii_drawing_stays_ascii(self, project_dir, search_path):
        repositories = {'project2': Repository(name='project2', version='2.x')}

        text = format_tree(info(project_dir, 'project2'), repositories, [search_path], glyphs=ASCII)

        text.encode('ascii')


class TestFormatOrigin:

    def test_a_colcon_pkg_key(self):
        origin = Origin(file=Path('/repos/nebula/main/core/colcon.pkg'), key='build-dependencies')
        assert format_origin(origin, Path('/repos/nebula/main')) == 'core/colcon.pkg (build-dependencies)'

    def test_a_cmakelists_line(self):
        origin = Origin(file=Path('/repos/nebula/main/core/CMakeLists.txt'), line=12)
        assert format_origin(origin, Path('/repos/nebula/main')) == 'core/CMakeLists.txt:12'

    def test_a_file_in_the_project_directory_itself(self):
        origin = Origin(file=Path('/repos/nebula/main/colcon.pkg'), key='dependencies')
        assert format_origin(origin, Path('/repos/nebula/main')) == 'colcon.pkg (dependencies)'

    def test_without_a_project_directory(self):
        origin = Origin(file=Path('/repos/nebula/main/core/colcon.pkg'), key='dependencies')
        assert format_origin(origin) == str(Path('/repos/nebula/main/core/colcon.pkg')) + ' (dependencies)'

    def test_a_file_outside_the_project_directory(self):
        origin = Origin(file=Path('/elsewhere/colcon.pkg'), key='dependencies')
        assert format_origin(origin, Path('/repos/nebula/main')).startswith(str(Path('/elsewhere')))


class TestOriginsInTheTree:

    def repositories(self):
        return {'project2': Repository(name='project2', version='2.x')}

    def test_a_key_is_shown_under_the_dependency(self, project_dir, search_path):
        origins = {'project2': Origin(file=project_dir / 'core' / 'colcon.pkg', key='test-dependencies')}

        text = format_tree(
                info(project_dir, 'project2', origins=origins),
                self.repositories(), [search_path], project_dir=project_dir)

        assert 'core/colcon.pkg (test-dependencies)' in text

    def test_a_line_is_shown_under_the_dependency(self, project_dir, search_path):
        origins = {'project2': Origin(file=project_dir / 'core' / 'CMakeLists.txt', line=7)}

        text = format_tree(
                info(project_dir, 'project2', origins=origins),
                self.repositories(), [search_path], project_dir=project_dir)

        assert 'core/CMakeLists.txt:7' in text

    def test_the_origin_follows_its_dependency(self, project_dir, search_path):
        origins = {'project2': Origin(file=project_dir / 'core' / 'colcon.pkg', key='dependencies')}

        lines = format_tree(
                info(project_dir, 'project2', origins=origins),
                self.repositories(), [search_path], project_dir=project_dir).splitlines()

        position = next(index for index, line in enumerate(lines) if '2.x' in line)
        assert 'core/colcon.pkg (dependencies)' in lines[position + 1]

    def test_a_dependency_without_an_origin_carries_no_line(self, project_dir, search_path):
        text = format_tree(info(project_dir, 'project2'), self.repositories(), [search_path])

        assert 'colcon.pkg' not in text
        assert 'CMakeLists' not in text

    def test_the_branch_continues_past_a_middle_dependency(self, project_dir, search_path):
        origins = {
            'project2': Origin(file=project_dir / 'colcon.pkg', key='dependencies'),
            'Threads': Origin(file=project_dir / 'colcon.pkg', key='dependencies'),
        }

        lines = format_tree(
                info(project_dir, 'project2', 'Threads', origins=origins),
                self.repositories(), [search_path], project_dir=project_dir).splitlines()

        first, last = lines[-4:-2], lines[-2:]
        assert first[1].startswith(UNICODE.blank + UNICODE.pipe)
        assert last[1].startswith(UNICODE.blank + UNICODE.blank)

    def test_the_ascii_drawing_nests_too(self, project_dir, search_path):
        origins = {'project2': Origin(file=project_dir / 'colcon.pkg', key='dependencies')}

        text = format_tree(
                info(project_dir, 'project2', origins=origins),
                self.repositories(), [search_path], project_dir=project_dir, glyphs=ASCII)

        text.encode('ascii')
        assert 'colcon.pkg (dependencies)' in text

# Copyright 2019 Ricardo González
# Licensed under the Apache License, Version 2.0

import shutil

import pytest
import yaml

from colocon.resolve import (
    DEFAULT_VERSION,
    DEPENDENCY_KEYS,
    ProjectInfo,
    Repository,
    find_package_dirs,
    find_worktree,
    read_project_info,
    read_repositories,
    resolve_paths,
    select_dependencies,
)

#: A project name that is absent from the search path fixture.
UNKNOWN_PROJECT = 'project9'


class TestReadProjectInfo:

    def test_absent_file(self, project_dir):
        assert read_project_info(project_dir) is None

    def test_without_name(self, write_pkg):
        assert read_project_info(write_pkg(dependencies=['project2'])) is None

    def test_empty_file(self, project_dir):
        (project_dir / 'colcon.pkg').write_text('')
        assert read_project_info(project_dir) is None

    def test_without_dependencies(self, write_pkg):
        project_dir = write_pkg(name='project1')
        assert read_project_info(project_dir) == ProjectInfo(
                name='project1', dependencies=(), package_dirs=(project_dir.resolve(),))

    def test_with_dependencies(self, write_pkg):
        project_dir = write_pkg(name='project1', dependencies=['project2', 'project3'])
        info = read_project_info(project_dir)
        assert info == ProjectInfo(
                name='project1',
                dependencies=('project2', 'project3'),
                package_dirs=(project_dir.resolve(),))

    def test_relative_project_dir_becomes_absolute(self, monkeypatch, write_pkg):
        project_dir = write_pkg(name='project1')
        monkeypatch.chdir(project_dir)

        assert read_project_info('.').package_dirs == (project_dir.resolve(),)


class TestDependencyKeys:
    """`colcon.pkg` may declare dependencies for one phase only."""

    def test_every_key_is_supported(self):
        assert DEPENDENCY_KEYS == (
            'dependencies', 'build-dependencies', 'run-dependencies', 'test-dependencies')

    @pytest.mark.parametrize('key', DEPENDENCY_KEYS)
    def test_key_is_read_on_its_own(self, key, write_pkg):
        info = read_project_info(write_pkg(**{'name': 'project1', key: ['project2']}))
        assert info.dependencies == ('project2',)

    def test_keys_are_joined(self, write_pkg):
        project_dir = write_pkg(**{
            'name': 'project1',
            'dependencies': ['project2'],
            'build-dependencies': ['project3'],
            'run-dependencies': ['project4'],
            'test-dependencies': ['project5'],
        })

        info = read_project_info(project_dir)

        assert info.dependencies == ('project2', 'project3', 'project4', 'project5')

    def test_a_dependency_of_several_phases_is_kept_once(self, write_pkg):
        project_dir = write_pkg(**{
            'name': 'project1',
            'dependencies': ['project2'],
            'build-dependencies': ['project2', 'project3'],
            'test-dependencies': ['project3'],
        })

        info = read_project_info(project_dir)

        assert info.dependencies == ('project2', 'project3')

    def test_an_empty_key_is_ignored(self, project_dir):
        (project_dir / 'colcon.pkg').write_text(
                'name: project1\ndependencies:\n  - project2\ntest-dependencies:\n')

        assert read_project_info(project_dir).dependencies == ('project2',)

    def test_without_any_key(self, write_pkg):
        assert read_project_info(write_pkg(name='project1')).dependencies == ()

    def test_other_keys_are_left_alone(self, write_pkg):
        # `type` and `hooks` are colcon's business, not colocon's.
        project_dir = write_pkg(**{
            'name': 'project1',
            'type': 'cmake',
            'hooks': ['share/hook.sh'],
            'test-dependencies': ['project2'],
        })

        assert read_project_info(project_dir).dependencies == ('project2',)


class TestPackagesInSubdirectories:
    """Without a `colcon.pkg` of its own, a project is a set of packages."""

    def write_package(self, project_dir, subdirectory, **content):
        package_dir = project_dir / subdirectory
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / 'colcon.pkg').write_text(yaml.dump(content))
        return package_dir

    def test_finds_packages_one_level_down(self, project_dir):
        core = self.write_package(project_dir, 'core', name='project1_core')
        tools = self.write_package(project_dir, 'tools', name='project1_tools')

        assert find_package_dirs(project_dir) == (core, tools)

    def test_ignores_a_subdirectory_without_a_package(self, project_dir):
        core = self.write_package(project_dir, 'core', name='project1_core')
        (project_dir / 'docs').mkdir()

        assert find_package_dirs(project_dir) == (core,)

    def test_ignores_deeper_levels(self, project_dir):
        # colcon crawls deeper on its own once pointed at a package.
        self.write_package(project_dir, 'core/nested', name='nested')

        assert find_package_dirs(project_dir) == ()

    def test_absent_directory(self, tmp_path):
        assert find_package_dirs(tmp_path / 'absent') == ()

    def test_dependencies_of_every_package_are_joined(self, project_dir):
        self.write_package(project_dir, 'core', name='project1_core', dependencies=['project2'])
        self.write_package(project_dir, 'tools', name='project1_tools',
                           **{'test-dependencies': ['project3']})

        info = read_project_info(project_dir)

        assert info.dependencies == ('project2', 'project3')

    def test_a_dependency_of_several_packages_is_kept_once(self, project_dir):
        self.write_package(project_dir, 'core', name='project1_core', dependencies=['project2'])
        self.write_package(project_dir, 'tools', name='project1_tools', dependencies=['project2', 'project3'])

        assert read_project_info(project_dir).dependencies == ('project2', 'project3')

    def test_every_package_is_handed_to_colcon(self, project_dir):
        core = self.write_package(project_dir, 'core', name='project1_core')
        tools = self.write_package(project_dir, 'tools', name='project1_tools')

        # `--paths` does not recurse, so each package needs its own path.
        assert read_project_info(project_dir).package_dirs == (core, tools)

    def test_project_is_named_after_the_repository_directory(self, project_dir):
        # project_dir is `<tmp>/project1/main`, so the repos file is project1.repos.
        self.write_package(project_dir, 'core', name='project1_core')

        assert read_project_info(project_dir).name == 'project1'

    def test_a_package_without_dependencies(self, project_dir):
        self.write_package(project_dir, 'core', name='project1_core')

        assert read_project_info(project_dir).dependencies == ()

    def test_no_package_anywhere(self, project_dir):
        (project_dir / 'docs').mkdir()

        assert read_project_info(project_dir) is None

    def test_a_root_package_wins_over_the_subdirectories(self, project_dir, write_pkg):
        self.write_package(project_dir, 'core', name='project1_core', dependencies=['project3'])
        write_pkg(name='project1', dependencies=['project2'])

        info = read_project_info(project_dir)

        assert info.name == 'project1'
        assert info.dependencies == ('project2',)
        assert info.package_dirs == (project_dir.resolve(),)


class TestReadRepositories:

    def test_absent_file(self, project_dir):
        assert read_repositories(project_dir, 'project1') == {}

    def test_empty_file(self, project_dir):
        (project_dir / 'project1.repos').write_text('')
        assert read_repositories(project_dir, 'project1') == {}

    def test_version_is_read(self, project_dir, write_repos):
        write_repos('project1', {'project2': {'version': '2.x'}})
        repositories = read_repositories(project_dir, 'project1')
        assert repositories['project2'] == Repository(name='project2', version='2.x')

    def test_version_falls_back_to_default(self, project_dir, write_repos):
        write_repos('project1', {'project2': {'url': 'git@example.com:project2.git'}})
        assert read_repositories(project_dir, 'project1')['project2'].version == DEFAULT_VERSION

    def test_empty_entry_falls_back_to_default(self, project_dir, write_repos):
        write_repos('project1', {'project2': None})
        assert read_repositories(project_dir, 'project1')['project2'].version == DEFAULT_VERSION

    def test_numeric_version_is_coerced_to_str(self, project_dir):
        # YAML resolves an unquoted `1.0` to a float, which cannot build a path.
        (project_dir / 'project1.repos').write_text('repositories:\n  project2:\n    version: 1.0\n')
        assert read_repositories(project_dir, 'project1')['project2'].version == '1.0'

    def test_recursive_flag(self, project_dir, write_repos):
        write_repos('project1', {
            'project2': {'version': '2.x', 'recursive': True},
            'project3': {'version': '3.x'},
        })
        repositories = read_repositories(project_dir, 'project1')
        assert repositories['project2'].recursive is True
        assert repositories['project3'].recursive is False


class TestSelectDependencies:

    REPOSITORIES = {
        'project2': Repository(name='project2', version='2.x'),
        'project3': Repository(name='project3', version='3.x'),
        'project1': Repository(name='project1', version='master'),
    }

    def test_inner_join(self):
        selected = select_dependencies(self.REPOSITORIES, ['project2'])
        assert list(selected) == ['project2']

    def test_dependency_absent_from_repos_is_ignored(self):
        selected = select_dependencies(self.REPOSITORIES, ['project2', 'unlisted'])
        assert list(selected) == ['project2']

    def test_repository_absent_from_the_dependencies_is_ignored(self):
        # A repos file may pin more repositories than this project needs.
        selected = select_dependencies(self.REPOSITORIES, ['project2'])
        assert 'project3' not in selected

    def test_the_projects_own_entry_is_not_selected(self):
        selected = select_dependencies(self.REPOSITORIES, ['project2'])
        assert 'project1' not in selected

    def test_without_dependencies(self):
        assert select_dependencies(self.REPOSITORIES, ()) == {}


class TestFindWorktree:

    def test_wanted_version(self, search_path):
        worktree = find_worktree(Repository(name='project2', version='2.x'), [search_path])
        assert worktree == search_path / 'project2' / '2.x'

    def test_falls_back_to_default_version(self, search_path):
        worktree = find_worktree(Repository(name='project2', version='feature/absent'), [search_path])
        assert worktree == search_path / 'project2' / DEFAULT_VERSION

    def test_project_without_any_worktree(self, search_path):
        assert find_worktree(Repository(name='no_worktree', version='master'), [search_path]) is None

    def test_unknown_project(self, search_path):
        assert find_worktree(Repository(name=UNKNOWN_PROJECT, version='master'), [search_path]) is None

    def test_searches_every_search_path(self, tmp_path, search_path):
        empty = tmp_path / 'empty'
        empty.mkdir()
        worktree = find_worktree(Repository(name='project2', version='2.x'), [empty, search_path])
        assert worktree == search_path / 'project2' / '2.x'

    def test_continues_when_a_search_path_lacks_the_worktree(self, tmp_path, search_path):
        # The project exists in the first search path, but the worktree does not.
        other = tmp_path / 'other'
        (other / 'project2').mkdir(parents=True)
        worktree = find_worktree(Repository(name='project2', version='2.x'), [other, search_path])
        assert worktree == search_path / 'project2' / '2.x'


class TestResolvePaths:

    def repositories(self, **overrides):
        repositories = {
            'project2': Repository(name='project2', version='2.x'),
            'project4': Repository(name='project4', version='4.x', recursive=True),
            UNKNOWN_PROJECT: Repository(name=UNKNOWN_PROJECT, version='master'),
        }
        repositories.update(overrides)
        return repositories

    def test_splits_recursive_dependencies(self, project_dir, search_path):
        info = ProjectInfo(name='project1', dependencies=('project2', 'project4'), package_dirs=(project_dir,))
        resolved = resolve_paths(info, self.repositories(), [search_path])

        assert resolved.paths == (str(search_path / 'project2' / '2.x'), str(project_dir))
        assert resolved.recursive_paths == (str(search_path / 'project4' / '4.x'),)

    def test_reports_missing_dependencies(self, project_dir, search_path):
        info = ProjectInfo(name='project1', dependencies=('project2', UNKNOWN_PROJECT), package_dirs=(project_dir,))
        resolved = resolve_paths(info, self.repositories(), [search_path])

        assert resolved.missing == (UNKNOWN_PROJECT,)
        assert str(search_path / UNKNOWN_PROJECT) not in resolved.paths

    def test_project_is_always_the_last_path(self, project_dir, search_path):
        info = ProjectInfo(name='project1', dependencies=('project2',), package_dirs=(project_dir,))
        resolved = resolve_paths(info, self.repositories(), [search_path])

        assert resolved.paths[-1] == str(project_dir)



class TestDependencyChain:
    """A chain of three levels: project1 -> project2 -> project3.

    `colocon` reads the ``colcon.pkg`` of the project it is run from and no
    other, so it never walks the chain itself: it hands `colcon` the paths of
    whatever the root project and its *repos* file agree upon, and `colcon`
    resolves the graph from there. These tests pin that down.
    """

    REPOSITORIES = {
        'project2': Repository(name='project2', version='2.x'),
        'project3': Repository(name='project3', version='3.x'),
    }

    def test_whole_chain_declared_by_the_root_project(self, chain, project_dir, search_path):
        info = ProjectInfo(name='project1', dependencies=('project2', 'project3'), package_dirs=(project_dir,))
        resolved = resolve_paths(info, self.REPOSITORIES, [search_path])

        assert resolved.paths == (str(chain.project2), str(chain.project3), str(project_dir))
        assert resolved.missing == ()

    def test_every_level_uses_its_own_version(self, chain, project_dir, search_path):
        info = ProjectInfo(name='project1', dependencies=('project2', 'project3'), package_dirs=(project_dir,))
        resolved = resolve_paths(info, self.REPOSITORIES, [search_path])

        # Both projects also have a `master` worktree, which must not be taken.
        assert resolved.paths[:2] == (str(chain.project2), str(chain.project3))
        assert not any(path.endswith(DEFAULT_VERSION) for path in resolved.paths)

    def test_indirect_level_is_left_to_colcon(self, chain, project_dir, search_path):
        # project1 declares only project2; project3 is project2's own
        # dependency, and `colocon` does not read project2's `colcon.pkg`.
        info = ProjectInfo(name='project1', dependencies=('project2',), package_dirs=(project_dir,))
        resolved = resolve_paths(info, self.REPOSITORIES, [search_path])

        assert resolved.paths == (str(chain.project2), str(project_dir))
        assert str(chain.project3) not in resolved.paths
        # It is not reported as missing either: it was never looked for.
        assert resolved.missing == ()

    def test_a_middle_level_can_be_recursive(self, chain, project_dir, search_path):
        repositories = dict(self.REPOSITORIES, project2=Repository(name='project2', version='2.x', recursive=True))
        info = ProjectInfo(name='project1', dependencies=('project2', 'project3'), package_dirs=(project_dir,))
        resolved = resolve_paths(info, repositories, [search_path])

        assert resolved.recursive_paths == (str(chain.project2),)
        assert resolved.paths == (str(chain.project3), str(project_dir))

    def test_a_broken_level_does_not_hide_the_others(self, chain, project_dir, search_path):
        repositories = dict(self.REPOSITORIES)
        repositories[UNKNOWN_PROJECT] = Repository(name=UNKNOWN_PROJECT, version='master')
        info = ProjectInfo(
                name='project1',
                dependencies=('project2', UNKNOWN_PROJECT, 'project3'),
                package_dirs=(project_dir,))
        resolved = resolve_paths(info, repositories, [search_path])

        assert resolved.missing == (UNKNOWN_PROJECT,)
        assert resolved.paths == (str(chain.project2), str(chain.project3), str(project_dir))

    def test_levels_spread_over_several_search_paths(self, chain, tmp_path, project_dir, search_path):
        # Each level may live in a different search path.
        other = tmp_path / 'other'
        other.mkdir()
        shutil.move(str(search_path / 'project3'), str(other / 'project3'))
        moved = other / 'project3' / '3.x'

        info = ProjectInfo(name='project1', dependencies=('project2', 'project3'), package_dirs=(project_dir,))
        resolved = resolve_paths(info, self.REPOSITORIES, [search_path, other])

        assert resolved.paths == (str(chain.project2), str(moved), str(project_dir))

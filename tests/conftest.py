# Copyright 2019 Ricardo González
# Licensed under the Apache License, Version 2.0

from types import SimpleNamespace

import pytest
import yaml

#: Projects of the search path fixture, with the worktrees checked out of each.
#: Every project offers `master` besides its own version, so that a test asking
#: for a version proves the version was honoured and not just the fallback.
WORKTREES = {
    'project2': ['master', '2.x'],
    'project3': ['master', '3.x'],
    'project4': ['master', '4.x'],
    'no_worktree': [],
}


@pytest.fixture
def search_path(tmp_path):
    """A search path holding several projects, each with its worktrees."""
    root = tmp_path / 'repos'
    for project, versions in WORKTREES.items():
        (root / project).mkdir(parents=True)
        for version in versions:
            (root / project / version).mkdir()
    return root


@pytest.fixture
def project_dir(tmp_path):
    """The worktree `colocon` is run from."""
    path = tmp_path / 'project1' / 'main'
    path.mkdir(parents=True)
    return path


@pytest.fixture
def write_pkg(project_dir):
    """Write a ``colcon.pkg`` into the project directory."""
    def write(**content):
        (project_dir / 'colcon.pkg').write_text(yaml.dump(content))
        return project_dir
    return write


@pytest.fixture
def write_repos(project_dir):
    """Write a *repos* file into the project directory."""
    def write(project_name, repositories):
        path = project_dir / (project_name + '.repos')
        path.write_text(yaml.dump({'repositories': repositories}))
        return path
    return write


@pytest.fixture
def chain(search_path):
    """A chain of dependencies: project1 -> project2 -> project3.

    Each level declares the next one in its own ``colcon.pkg``, the way a real
    checkout does. `colocon` only ever reads the ``colcon.pkg`` of the project
    it is run from, so these let a test tell what `colocon` reads apart from
    what it leaves to `colcon`. The project directory is left alone, for the
    test to describe project1 as it needs.
    """
    levels = SimpleNamespace(
        project2=search_path / 'project2' / '2.x',
        project3=search_path / 'project3' / '3.x',
    )
    (levels.project2 / 'colcon.pkg').write_text(yaml.dump({'name': 'project2', 'dependencies': ['project3']}))
    (levels.project3 / 'colcon.pkg').write_text(yaml.dump({'name': 'project3'}))
    return levels

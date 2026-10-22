# Copyright 2019 Ricardo González
# Licensed under the Apache License, Version 2.0

"""What keeps the package importable on the oldest Python it supports.

`colocon` writes its annotations in the shorter ``str | Path`` form, which the
interpreter only understands from 3.10 onwards. What makes that safe on 3.9 is
``from __future__ import annotations``: every annotation is then left as text
and never evaluated. A module adding an annotation without it would import
fine on a developer's machine and fail on an older one, so it is checked here
rather than found by whoever runs that older one.

Outside an annotation the shorter form is evaluated and really does need 3.10 —
see the ``PathLike`` alias of `colocon.resolve`. That one, no test can see: it
is caught by mypy, which only reports it when run on the oldest Python, as the
lint job of the workflow does.
"""

import ast
from pathlib import Path

import pytest

import colocon

SOURCES = sorted(Path(colocon.__file__).parent.glob('*.py'))


def annotations_of(tree):
    """Every annotation written in `tree`."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.AnnAssign, ast.arg)):
            found.append(node.annotation)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.append(node.returns)
    return [annotation for annotation in found if annotation is not None]


def postpones_annotations(tree):
    """Whether `tree` begins by asking for its annotations to be left as text."""
    return any(
        isinstance(node, ast.ImportFrom) and node.module == '__future__'
        and any(alias.name == 'annotations' for alias in node.names)
        for node in tree.body
    )


def test_every_source_was_found():
    assert {source.name for source in SOURCES} >= {'cli.py', 'config.py', 'resolve.py', 'runner.py', 'tree.py'}


@pytest.mark.parametrize('source', SOURCES, ids=lambda source: source.name)
def test_a_module_with_annotations_postpones_them(source):
    tree = ast.parse(source.read_text())

    if not annotations_of(tree):
        return

    assert postpones_annotations(tree), (
        f'{source.name} is annotated without `from __future__ import annotations`, '
        f'so its annotations are evaluated on import and `X | Y` among them would '
        f'fail on Python 3.9')

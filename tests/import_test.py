from __future__ import annotations

import importlib.metadata


def test_import():
    import anysub

    del anysub


def test_version():
    import anysub

    assert anysub.__version__ == importlib.metadata.version("anysub")

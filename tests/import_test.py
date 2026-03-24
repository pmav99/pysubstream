from __future__ import annotations

import importlib.metadata


def test_import():
    import pysubstream

    del pysubstream


def test_version():
    import pysubstream

    assert pysubstream.__version__ == importlib.metadata.version("pysubstream")

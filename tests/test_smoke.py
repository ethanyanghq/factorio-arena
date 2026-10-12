import tomllib
from pathlib import Path

import factorio_arena

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def test_package_exposes_a_version():
    assert factorio_arena.__version__


def test_package_version_matches_pyproject():
    declared_version = tomllib.loads(PYPROJECT.read_text())["project"]["version"]
    assert factorio_arena.__version__ == declared_version

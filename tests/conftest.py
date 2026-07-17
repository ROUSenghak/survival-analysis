import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))


@pytest.fixture(scope="session")
def cfg():
    from boamp.config import load_config
    return load_config(REPO)

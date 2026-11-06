import pytest


@pytest.fixture
def raw_dir(tmp_path):
    return tmp_path / "raw"

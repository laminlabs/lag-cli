import shutil

import lamindb as ln
import pytest


@pytest.fixture(scope="session")
def setup_lamindb():
    ln.setup.init(storage="./testagentdb")
    yield
    shutil.rmtree("./default_storage_unit_core")
    ln.setup.delete("testagentdb", force=True)

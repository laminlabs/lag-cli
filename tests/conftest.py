import shutil

import lamindb as ln
import pytest


@pytest.fixture(scope="session")
def setup_lamindb():
    ln.setup.init(storage="./testagentdb")
    yield
    shutil.rmtree("./testagentdb")
    ln.setup.delete("testagentdb", force=True)

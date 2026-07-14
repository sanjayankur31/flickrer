import sqlite3

import pytest

from flickrer.db import _CREATE_TABLES


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(_CREATE_TABLES)
    yield c
    c.close()

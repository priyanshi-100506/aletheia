import sqlite3
from repository import active_users


def test_active_users_returns_only_active_rows():
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE users (name TEXT, status TEXT)")
    connection.executemany(
        "INSERT INTO users VALUES (?, ?)",
        [("Ada", "active"), ("Grace", "inactive")],
    )
    assert active_users(connection) == [("Ada",)]

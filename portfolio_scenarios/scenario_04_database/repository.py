import sqlite3


def active_users(connection):
    return connection.execute(
        "SELECT name FROM users WHERE status = 'inactive' ORDER BY name"
    ).fetchall()

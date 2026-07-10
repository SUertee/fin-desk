from app.connectors.postgres.connection import _ensure_schema


class FakeCursor:
    def __init__(self):
        self.executed = []

    def execute(self, sql):
        self.executed.append(sql)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConnection:
    def __init__(self):
        self.cursor_obj = FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True


def test_ensure_schema_executes_checked_in_schema_file():
    conn = FakeConnection()

    _ensure_schema(conn)

    assert conn.committed is True
    assert len(conn.cursor_obj.executed) == 1
    assert "statement_import_records" in conn.cursor_obj.executed[0]
    assert "session_memory" in conn.cursor_obj.executed[0]

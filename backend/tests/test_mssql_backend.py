import asyncio
import json
from types import SimpleNamespace

from app.config import Settings, settings
from app.db.mssql import (
    AsyncCursor,
    _apply_update,
    _index_expression,
    _matches,
    _sql_filter,
    _table_name,
    build_database_url,
    delete_employee_preserving_history_transactional,
    delete_attendance_submission_transactional,
)


def test_document_filter_supports_nested_boolean_and_regex_queries():
    document = {
        "_id": "record-1",
        "status": "pending",
        "employee_id": "EMP001",
        "name": "Alice Supervisor",
    }

    assert _matches(document, {
        "$and": [
            {"status": {"$in": ["pending", "retry"]}},
            {"employee_id": {"$ne": "EMP002"}},
            {"$or": [{"name": {"$regex": "alice", "$options": "i"}}]},
        ],
        "$nor": [{"status": "completed"}],
    })
    assert not _matches(document, {"status": {"$in": ["completed"]}})


def test_scalar_query_compiles_to_parameterized_sql():
    parameters = {}
    where = _sql_filter(
        {
            "employee_id": {"$in": ["EMP001", "EMP002"]},
            "attendance_date": {"$gte": "2026-01-01"},
            "review_status": {"$ne": "superseded"},
        },
        parameters,
    )

    assert where is not None
    assert "IN (:p0, :p1)" in where
    assert parameters == {
        "p0": "EMP001",
        "p1": "EMP002",
        "p2": "2026-01-01",
        "p3": "superseded",
    }
    assert _sql_filter({"name": {"$regex": "Alice", "$options": "i"}}, {}) is None


def test_sparse_unique_submission_ids_are_normalized_for_sql_indexes():
    parameters = {}
    where = _sql_filter(
        {"event_id": "event-123"}, parameters, collection="submissions"
    )

    assert where is not None
    assert "[ixv_" in where
    assert parameters == {"p0": "V:event-123"}


def test_sparse_unique_index_expression_has_balanced_computed_column_parentheses():
    expression = _index_expression("event_id", sparse=True)

    assert expression.startswith("(CONVERT(")
    assert expression.endswith("))")


def test_cursor_supports_projection_and_document_sort_signature():
    class FakeCollection:
        async def _find_documents(self, _query):
            return [
                {"username": "zoe", "role": "viewer"},
                {"username": "amy", "role": "manual_team"},
            ]

    async def collect():
        cursor = AsyncCursor(
            FakeCollection(), {}, {"_id": 0, "username": 1}
        ).sort("username", 1)
        return [item async for item in cursor]

    assert asyncio.run(collect()) == [{"username": "amy"}, {"username": "zoe"}]


def test_update_operators_preserve_document_fields_and_append_history():
    original = {"_id": "row-1", "history": [{"status": "created"}], "attempt": 1}
    changed = _apply_update(original, {
        "$set": {"status": "retry"},
        "$setOnInsert": {"created_at": "now"},
        "$inc": {"attempt": 1},
        "$push": {"history": {"status": "retry"}},
    })

    assert changed == {
        "_id": "row-1",
        "history": [{"status": "created"}, {"status": "retry"}],
        "attempt": 2,
        "status": "retry",
    }


def test_mssql_url_uses_configured_local_database_and_integrated_auth(monkeypatch):
    monkeypatch.setattr(settings, "mssql_server", "localhost")
    monkeypatch.setattr(settings, "mssql_database", "attendance_agent_local")
    monkeypatch.setattr(settings, "mssql_trusted_connection", True)
    url = build_database_url()

    assert url.drivername == "mssql+aioodbc"
    assert url.host == "localhost"
    assert url.database == "attendance_agent_local"
    assert url.username is None
    assert url.password is None
    assert url.query["Trusted_Connection"] == "yes"


def test_settings_use_sql_server_as_the_only_database(monkeypatch):
    monkeypatch.setenv("MSSQL_SERVER", "sql-prod.example.internal")

    assert Settings(_env_file=None).mssql_server == "sql-prod.example.internal"


def test_attendance_delete_uses_the_actual_override_collection_table(monkeypatch):
    class FakeResult:
        def __init__(self, row=None, rowcount=0):
            self.row = row
            self.rowcount = rowcount

        def first(self):
            return self.row

    class FakeConnection:
        def __init__(self):
            self.statements = []

        async def execute(self, statement, _parameters=None):
            sql = str(statement)
            self.statements.append(sql)
            if sql.startswith("SELECT [data_json]"):
                return FakeResult(SimpleNamespace(data_json=json.dumps({
                    "employee_id": "EMP001",
                    "attendance_date": "2026-10-24",
                })))
            if sql.startswith("DELETE FROM [dbo].[attendance_submissions]"):
                return FakeResult(rowcount=1)
            return FakeResult()

    class FakeEngine:
        def __init__(self):
            self.connection = FakeConnection()

        async def __aenter__(self):
            return self.connection

        async def __aexit__(self, *_args):
            return False

        def begin(self):
            return self

    engine = FakeEngine()
    monkeypatch.setattr("app.db.mssql.get_engine", lambda: engine)

    assert asyncio.run(delete_attendance_submission_transactional("a" * 24))
    assert engine.connection.statements[-1].startswith(
        f"DELETE FROM {_table_name('attendance_overrides')}"
    )


def test_employee_delete_preserves_attendance_and_overrides_atomically(monkeypatch):
    class FakeResult:
        def __init__(self, row=None, rowcount=0, count=0):
            self.row = row
            self.rowcount = rowcount
            self.count = count

        def first(self):
            return self.row

        def scalar_one(self):
            return self.count

    class FakeConnection:
        def __init__(self, child_count=0):
            self.child_count = child_count
            self.statements = []

        async def execute(self, statement, _parameters=None):
            sql = str(statement)
            self.statements.append(sql)
            if sql.startswith("SELECT [id] FROM [dbo].[attendance_roster]"):
                return FakeResult(SimpleNamespace(id="roster-row"))
            if sql.startswith("SELECT COUNT_BIG(*)"):
                return FakeResult(count=self.child_count)
            return FakeResult(rowcount=1)

    class FakeEngine:
        def __init__(self, child_count=0):
            self.connection = FakeConnection(child_count)

        async def __aenter__(self):
            return self.connection

        async def __aexit__(self, *_args):
            return False

        def begin(self):
            return self

    engine = FakeEngine()
    monkeypatch.setattr("app.db.mssql.get_engine", lambda: engine)

    assert asyncio.run(delete_employee_preserving_history_transactional("EMP002")) == 0
    deletes = [sql for sql in engine.connection.statements if sql.startswith("DELETE")]
    assert len(deletes) == 2
    assert any("attendance_face_embeddings" in sql for sql in deletes)
    assert any("attendance_roster" in sql for sql in deletes)
    assert all("attendance_submissions" not in sql for sql in deletes)
    assert all("attendance_attendance_overrides" not in sql for sql in deletes)

    blocked_engine = FakeEngine(child_count=2)
    monkeypatch.setattr("app.db.mssql.get_engine", lambda: blocked_engine)
    assert asyncio.run(
        delete_employee_preserving_history_transactional("EMP002")
    ) == 2
    assert not any(
        sql.startswith("DELETE") for sql in blocked_engine.connection.statements
    )

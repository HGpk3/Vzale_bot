import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable


def using_postgres() -> bool:
    return bool(os.getenv("DATABASE_URL"))


def _adapt_sql(query: str) -> str | None:
    q = query.strip()
    was_insert_or_ignore = bool(re.search(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", q, flags=re.I))

    # SQLite PRAGMAs are not relevant in Postgres.
    if re.match(r"^PRAGMA\s+(journal_mode|synchronous|busy_timeout|foreign_keys)", q, flags=re.I):
        return None

    q = re.sub(r"\bCOLLATE\s+NOCASE\b", "", q, flags=re.I)
    q = re.sub(r"datetime\('now'\)", "CURRENT_TIMESTAMP", q, flags=re.I)
    q = re.sub(r"\bINSERT\s+OR\s+IGNORE\s+INTO\b", "INSERT INTO", q, flags=re.I)

    # SQLite-specific helper query.
    q = re.sub(r"SELECT\s+last_insert_rowid\(\)", "SELECT LASTVAL()", q, flags=re.I)

    # SQLite placeholders -> psycopg placeholders.
    q = q.replace("?", "%s")
    if was_insert_or_ignore and "ON CONFLICT" not in q.upper():
        q = q.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return q


def _is_sqlite_master_table_check(query: str) -> bool:
    q = query.lower()
    return "from sqlite_master" in q and "type='table'" in q


def _extract_table_from_pragma(query: str) -> str | None:
    m = re.search(r"PRAGMA\s+table_info\(([^)]+)\)", query, flags=re.I)
    if not m:
        return None
    return m.group(1).strip().strip('"').strip("'")


@dataclass
class _SyntheticAsyncCursor:
    rows: list[tuple[Any, ...]]

    def __post_init__(self) -> None:
        self._idx = 0
        self.rowcount = len(self.rows)

    async def fetchone(self):
        if self._idx >= len(self.rows):
            return None
        row = self.rows[self._idx]
        self._idx += 1
        return row

    async def fetchall(self):
        if self._idx == 0:
            self._idx = len(self.rows)
            return list(self.rows)
        rows = self.rows[self._idx :]
        self._idx = len(self.rows)
        return rows

    async def close(self):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        row = await self.fetchone()
        if row is None:
            raise StopAsyncIteration
        return row


class _AsyncCursor:
    def __init__(self, cur):
        self._cur = cur

    async def fetchone(self):
        return await self._cur.fetchone()

    async def fetchall(self):
        return await self._cur.fetchall()

    async def close(self):
        await self._cur.close()

    @property
    def rowcount(self):
        return self._cur.rowcount

    def __aiter__(self):
        return self

    async def __anext__(self):
        row = await self._cur.fetchone()
        if row is None:
            raise StopAsyncIteration
        return row


class _AsyncExecuteOp:
    def __init__(self, conn: "_AsyncPgConn", query: str, params=(), many: bool = False):
        self._conn = conn
        self._query = query
        self._params = params
        self._many = many
        self._cursor = None

    async def _run(self):
        if self._cursor is None:
            self._cursor = await self._conn._execute_internal(self._query, self._params, many=self._many)
        return self._cursor

    def __await__(self):
        return self._run().__await__()

    async def __aenter__(self):
        return await self._run()

    async def __aexit__(self, exc_type, exc, tb):
        if self._cursor is not None:
            await self._cursor.close()


class _AsyncPgConn:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._conn = None

    async def __aenter__(self):
        from psycopg import AsyncConnection
        self._conn = await AsyncConnection.connect(self._dsn)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._conn is None:
            return
        if exc_type is None:
            await self._conn.commit()
        else:
            await self._conn.rollback()
        await self._conn.close()

    def execute(self, query: str, params: Iterable[Any] | tuple[Any, ...] = ()):  # aiosqlite-compatible
        return _AsyncExecuteOp(self, query, params, many=False)

    def executemany(self, query: str, seq_of_params: Iterable[Iterable[Any]]):
        return _AsyncExecuteOp(self, query, list(seq_of_params), many=True)

    async def commit(self):
        await self._conn.commit()

    async def close(self):
        await self._conn.close()

    async def _execute_internal(self, query: str, params, many: bool = False):
        if self._conn is None:
            raise RuntimeError("Connection is not opened")

        if _is_sqlite_master_table_check(query):
            table = None
            if isinstance(params, (list, tuple)) and params:
                table = params[0]
            q2 = (
                "SELECT tablename AS name FROM pg_tables "
                "WHERE schemaname='public' AND tablename=%s"
            )
            cur = await self._conn.execute(q2, (table,))
            rows = await cur.fetchall()
            await cur.close()
            return _SyntheticAsyncCursor(rows)

        pragma_table = _extract_table_from_pragma(query)
        if pragma_table:
            q2 = (
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=%s "
                "ORDER BY ordinal_position"
            )
            cur = await self._conn.execute(q2, (pragma_table,))
            rows = await cur.fetchall()
            await cur.close()
            # SQLite PRAGMA table_info columns: cid, name, type, notnull, dflt_value, pk
            synth = [
                (idx, r[0], r[1], 0 if r[2] == "YES" else 1, r[3], 0)
                for idx, r in enumerate(rows)
            ]
            return _SyntheticAsyncCursor(synth)

        q2 = _adapt_sql(query)
        if q2 is None:
            return _SyntheticAsyncCursor([])

        if many:
            cur = await self._conn.cursor()
            await cur.executemany(q2, params)
            return _AsyncCursor(cur)

        cur = await self._conn.execute(q2, tuple(params) if params else ())
        return _AsyncCursor(cur)


class _SyncCursor:
    def __init__(self, cur):
        self._cur = cur

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def rowcount(self):
        return self._cur.rowcount


class _SyncPgConn:
    def __init__(self, dsn: str):
        import psycopg
        self._conn = psycopg.connect(dsn)
        self.row_factory = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()

    def execute(self, query: str, params: Iterable[Any] | tuple[Any, ...] = ()):
        if _is_sqlite_master_table_check(query):
            table = params[0] if params else None
            cur = self._conn.execute(
                "SELECT tablename AS name FROM pg_tables WHERE schemaname='public' AND tablename=%s",
                (table,),
            )
            return _SyncCursor(cur)

        pragma_table = _extract_table_from_pragma(query)
        if pragma_table:
            cur = self._conn.execute(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=%s "
                "ORDER BY ordinal_position",
                (pragma_table,),
            )
            rows = cur.fetchall()
            class _Fake:
                def __init__(self, rows):
                    self._rows = rows
                    self.rowcount = len(rows)

                def fetchone(self):
                    return self._rows.pop(0) if self._rows else None

                def fetchall(self):
                    rows = list(self._rows)
                    self._rows = []
                    return rows

            synth = [
                (idx, r[0], r[1], 0 if r[2] == "YES" else 1, r[3], 0)
                for idx, r in enumerate(rows)
            ]
            return _Fake(synth)

        q2 = _adapt_sql(query)
        if q2 is None:
            class _Empty:
                rowcount = 0
                def fetchone(self):
                    return None
                def fetchall(self):
                    return []
            return _Empty()

        cur = self._conn.execute(q2, tuple(params) if params else ())
        return _SyncCursor(cur)

    def executemany(self, query: str, seq_of_params: Iterable[Iterable[Any]]):
        q2 = _adapt_sql(query)
        if q2 is None:
            return
        with self._conn.cursor() as cur:
            cur.executemany(q2, list(seq_of_params))

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def connect(sqlite_path: str):
    if using_postgres():
        return _AsyncPgConn(os.getenv("DATABASE_URL"))
    import aiosqlite as _aiosqlite
    return _aiosqlite.connect(sqlite_path)


def sync_connect(sqlite_path: str):
    if using_postgres():
        return _SyncPgConn(os.getenv("DATABASE_URL"))
    conn = sqlite3.connect(sqlite_path)
    return conn

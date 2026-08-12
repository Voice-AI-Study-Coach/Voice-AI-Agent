"""Postgres connection pool for Neon, with two small conveniences that keep
every call site in the codebase honest:

  - fetch_one / fetch_all / execute / execute_returning wrap the boilerplate
    of opening a cursor, running one statement, and closing it.
  - Rows come back as plain dicts (via psycopg's dict_row factory), matching
    the shape every controller already expects from the old Supabase client.

FastAPI runs sync route handlers and dependencies in a threadpool, so several
requests hit the database on different threads at once. ConnectionPool is
built for exactly that: each `pool.connection()` checks a connection out for
the block and returns it when the block exits, rather than every caller
needing its own connect/close dance.
"""

import os
import sys
from contextlib import contextmanager
from typing import Any, Iterable, Optional

from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from src.exception import CustomException

load_dotenv()

_DATABASE_URL = os.environ.get("NEON_DATABASE_URL")


def _configure(conn) -> None:
    """Runs once per new physical connection. register_vector lets a plain
    Python list of floats be bound straight into a `vector` column - without
    it psycopg has no idea how to adapt one."""
    register_vector(conn)


# min_size=0 lets the pool start even if Neon's endpoint is asleep at boot
# (Neon suspends idle compute); it wakes on first use instead of failing app
# startup entirely.
#
# check=ConnectionPool.check_connection runs a cheap "select" against a
# pooled connection before handing it to a caller. Neon can suspend its
# compute after a period of inactivity, which silently kills connections the
# pool is still holding - without this check, the next request to reuse one
# of those dead connections fails with "server closed the connection
# unexpectedly" instead of transparently getting a fresh one.
pool = ConnectionPool(
    conninfo=_DATABASE_URL,
    min_size=0,
    max_size=10,
    kwargs={"row_factory": dict_row, "autocommit": True},
    configure=_configure,
    check=ConnectionPool.check_connection,
    open=False,
)


def open_pool() -> None:
    pool.open(wait=True, timeout=15)


def close_pool() -> None:
    pool.close()


def ping() -> None:
    """Run a trivial real query against Neon.

    pool.open() establishes the pool object but does not necessarily force
    Neon's proxy to wake a suspended compute the way an actual query does -
    a bare TCP-level connect and a query are not the same signal to Neon's
    autoscaler. Called at startup and on a periodic keep-alive so requests
    do not pay Neon's cold-start cost (measured ~5s vs ~0.5s warm)."""
    with cursor() as cur:
        cur.execute("select 1")


@contextmanager
def cursor():
    with pool.connection() as conn:
        with conn.cursor() as cur:
            yield cur


def fetch_one(sql: str, params: Iterable[Any] = ()) -> Optional[dict]:
    try:
        with cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()
    except Exception as e:
        raise CustomException(e, sys)


def fetch_all(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    try:
        with cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    except Exception as e:
        raise CustomException(e, sys)


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    """Run a statement with no result set. Returns the affected row count."""
    try:
        with cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount
    except Exception as e:
        raise CustomException(e, sys)


def execute_returning(sql: str, params: Iterable[Any] = ()) -> Optional[dict]:
    """INSERT/UPDATE ... RETURNING one row. `sql` must include RETURNING."""
    try:
        with cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()
    except Exception as e:
        raise CustomException(e, sys)


def execute_returning_many(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    """INSERT ... RETURNING for a multi-row statement (executemany-style
    inserts built with a VALUES list)."""
    try:
        with cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()
    except Exception as e:
        raise CustomException(e, sys)

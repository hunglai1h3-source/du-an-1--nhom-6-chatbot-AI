import atexit
import os
import re
import threading
from collections.abc import Mapping

import psycopg
from dotenv import load_dotenv
import psycopg_pool


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL:
    raise RuntimeError(
        "Không tìm thấy DATABASE_URL. "
        "Hãy kiểm tra file .env hoặc Environment trên Render."
    )


class DatabaseRow(Mapping):
    """
    Cho phép dùng đồng thời:
    row["email"]
    row[0]
    dict(row)
    """

    def __init__(self, columns, values):
        self._columns = list(columns)
        self._values = tuple(values)
        self._data = dict(zip(self._columns, self._values))

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self._values[key]
        return self._data[key]

    def __iter__(self):
        return iter(self._columns)

    def __len__(self):
        return len(self._columns)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()


def convert_sql(sql):
    """
    Chuyển một số cú pháp SQLite đang có trong app.py
    sang cú pháp PostgreSQL.
    """

    converted = str(sql)

    # PostgreSQL dùng %s thay cho ?.
    converted = converted.replace("?", "%s")

    # Chuyển một số hàm ngày SQLite trong trang admin.
    converted = re.sub(
        r"date\('now'\s*,\s*'localtime'\s*,\s*'-6 day'\)",
        "(CURRENT_DATE - INTERVAL '6 days')::date",
        converted,
        flags=re.IGNORECASE,
    )

    converted = re.sub(
        r"date\('now'\s*,\s*'-6 day'\)",
        "(CURRENT_DATE - INTERVAL '6 days')::date",
        converted,
        flags=re.IGNORECASE,
    )

    converted = re.sub(
        r"date\('now'\s*,\s*'localtime'\)",
        "CURRENT_DATE",
        converted,
        flags=re.IGNORECASE,
    )

    converted = re.sub(
        r"date\('now'\)",
        "CURRENT_DATE",
        converted,
        flags=re.IGNORECASE,
    )

    converted = re.sub(
        r"date\(day\s*,\s*'\+1 day'\)",
        "(day + INTERVAL '1 day')::date",
        converted,
        flags=re.IGNORECASE,
    )

    return converted


TABLES_WITH_AUTO_ID = {
    "users",
    "health_profiles",
    "weight_logs",
    "water_logs",
    "reminders",
    "admin_audit_logs",
    "family_members",
    "chat_logs",
    "prompt_versions",
    "premium_orders",
    "user_notifications",
    "health_news",
    "symptom_logs",
    "health_metric_logs",
    "conversation_messages",
    "health_episodes",
    "health_episode_events",
    "personal_baselines",
    "personal_fact_states",
    "adaptive_severity_logs",
}


class CursorAdapter:
    def __init__(self, connection):
        self._connection = connection
        self._cursor = connection.cursor()
        self.lastrowid = None

    def execute(self, sql, parameters=None):
        converted_sql = convert_sql(sql)
        parameters = tuple(parameters or ())

        normalized_sql = converted_sql.strip().rstrip(";")
        insert_match = re.match(
            r"^\s*INSERT\s+INTO\s+([A-Za-z_][A-Za-z0-9_]*)",
            normalized_sql,
            flags=re.IGNORECASE,
        )

        should_return_id = False

        if insert_match:
            table_name = insert_match.group(1).lower()

            if (
                table_name in TABLES_WITH_AUTO_ID
                and " returning " not in normalized_sql.lower()
            ):
                normalized_sql += " RETURNING id"
                should_return_id = True

        self._cursor.execute(normalized_sql, parameters)

        if should_return_id:
            returned_row = self._cursor.fetchone()
            self.lastrowid = returned_row[0] if returned_row else None

        return self

    def _column_names(self):
        if not self._cursor.description:
            return []

        return [
            column.name
            if hasattr(column, "name")
            else column[0]
            for column in self._cursor.description
        ]

    def fetchone(self):
        row = self._cursor.fetchone()

        if row is None:
            return None

        return DatabaseRow(self._column_names(), row)

    def fetchall(self):
        rows = self._cursor.fetchall()
        columns = self._column_names()

        return [
            DatabaseRow(columns, row)
            for row in rows
        ]

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def close(self):
        self._cursor.close()


_pool = None
_pool_lock = threading.Lock()


def get_pool():
    """Lấy hoặc khởi tạo connection pool cho PostgreSQL (Thread-safe)."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                min_size = int(os.getenv("DB_POOL_MIN_SIZE", "1"))
                max_size = int(os.getenv("DB_POOL_MAX_SIZE", "6"))
                timeout = float(os.getenv("DB_POOL_TIMEOUT", "10.0"))
                max_idle = float(os.getenv("DB_POOL_MAX_IDLE", "300.0"))
                max_lifetime = float(os.getenv("DB_POOL_MAX_LIFETIME", "1800.0"))

                _pool = psycopg_pool.ConnectionPool(
                    conninfo=DATABASE_URL,
                    min_size=min_size,
                    max_size=max_size,
                    timeout=timeout,
                    max_idle=max_idle,
                    max_lifetime=max_lifetime,
                    open=True,
                )
    return _pool


def close_pool():
    """Đóng connection pool khi ứng dụng tắt."""
    global _pool
    with _pool_lock:
        if _pool is not None:
            try:
                if not _pool.closed:
                    _pool.close()
            except Exception:
                pass
            _pool = None


atexit.register(close_pool)


def get_pool_stats():
    """Lấy thống kê trạng thái connection pool phục vụ health check/monitoring."""
    global _pool
    if _pool is None:
        return {
            "status": "uninitialized",
            "pool_size": 0,
            "pool_available": 0,
            "requests_waiting": 0,
        }
    try:
        stats = _pool.get_stats()
        stats["status"] = "closed" if _pool.closed else "active"
        return stats
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }


class ConnectionAdapter:
    def __init__(self, raw_connection=None, pool=None):
        self._closed = False
        self._pool = pool

        if raw_connection is not None:
            self._connection = raw_connection
        elif self._pool is not None:
            self._connection = self._pool.getconn()
        else:
            self._connection = psycopg.connect(
                DATABASE_URL,
                connect_timeout=15,
            )

    def _is_conn_closed(self):
        closed_val = getattr(self._connection, "closed", False)
        if isinstance(closed_val, (bool, int)):
            return bool(closed_val)
        return False

    def execute(self, sql, parameters=None):
        cursor = CursorAdapter(self._connection)
        return cursor.execute(sql, parameters)

    def commit(self):
        if not self._closed and hasattr(self._connection, "commit") and not self._is_conn_closed():
            self._connection.commit()

    def rollback(self):
        if not self._closed and hasattr(self._connection, "rollback") and not self._is_conn_closed():
            self._connection.rollback()

    def close(self):
        if self._closed:
            return
        self._closed = True

        if self._pool is not None:
            # Luôn rollback giao dịch chưa commit trước khi trả kết nối về pool
            try:
                if hasattr(self._connection, "rollback") and not self._is_conn_closed():
                    self._connection.rollback()
            except Exception:
                pass
            try:
                self._pool.putconn(self._connection)
            except Exception:
                pass
        else:
            try:
                if hasattr(self._connection, "close"):
                    self._connection.close()
            except Exception:
                pass

    def __enter__(self):
        return self


    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type:
                self.rollback()
            else:
                self.commit()
        finally:
            self.close()


def get_connection(use_pool=None):
    """
    Lấy kết nối PostgreSQL được bọc bởi ConnectionAdapter.
    Mặc định sử dụng ConnectionPool để tái sử dụng kết nối TCP/SSL.
    """
    if use_pool is None:
        use_pool = os.getenv("USE_DB_POOL", "true").strip().lower() in ("true", "1", "yes")

    if use_pool:
        pool = get_pool()
        return ConnectionAdapter(pool=pool)

    return ConnectionAdapter()
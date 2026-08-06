import os
import re
from collections.abc import Mapping

import psycopg
from dotenv import load_dotenv


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


class ConnectionAdapter:
    def __init__(self):
        self._connection = psycopg.connect(
            DATABASE_URL,
            connect_timeout=15,
        )

    def execute(self, sql, parameters=None):
        cursor = CursorAdapter(self._connection)
        return cursor.execute(sql, parameters)

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()


def get_connection():
    return ConnectionAdapter()
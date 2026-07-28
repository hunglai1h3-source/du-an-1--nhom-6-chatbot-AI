import os
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def get_database_uri():
    """
    Nếu chạy trên Render sẽ dùng PostgreSQL.
    Nếu chạy trên máy cá nhân sẽ dùng SQLite.
    """

    database_url = os.getenv("DATABASE_URL")

    if database_url:
        # Render đôi khi trả về postgres://
        if database_url.startswith("postgres://"):
            database_url = database_url.replace(
                "postgres://",
                "postgresql://",
                1
            )
        return database_url

    # Chạy local
    return "sqlite:///users.db"
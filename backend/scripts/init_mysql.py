"""Create the POC MySQL database, all tables, and idempotent demo seed data.

Credentials are read from environment variables and are never persisted by this script.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from urllib.parse import quote_plus

import pymysql


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


def required(name: str, default: str = "") -> str:
    value = os.getenv(name, default).strip()
    if not value:
        raise RuntimeError(f"环境变量 {name} 未设置")
    return value


def main() -> None:
    host = required("MYSQL_HOST")
    port = int(required("MYSQL_PORT", "3306"))
    user = required("MYSQL_USER")
    password = required("MYSQL_PASSWORD")
    database = required("MYSQL_DATABASE", "contract_review_poc")
    if not re.fullmatch(r"[A-Za-z0-9_]+", database):
        raise RuntimeError("MYSQL_DATABASE 只能包含字母、数字和下划线")

    connection = pymysql.connect(host=host, port=port, user=user, password=password, charset="utf8mb4", connect_timeout=15)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        connection.commit()
    finally:
        connection.close()

    database_url = f"mysql+pymysql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{database}?charset=utf8mb4"
    os.environ["DATABASE_URL"] = database_url

    from sqlalchemy import func, select

    from app.database import Base, SessionLocal, engine
    from app.models import Contract, User
    from app.seed import seed_database

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_database(session)
        user_count = session.scalar(select(func.count()).select_from(User)) or 0
        contract_count = session.scalar(select(func.count()).select_from(Contract)) or 0
    print(f"database={database} tables={len(Base.metadata.tables)} users={user_count} contracts={contract_count}")


if __name__ == "__main__":
    main()
